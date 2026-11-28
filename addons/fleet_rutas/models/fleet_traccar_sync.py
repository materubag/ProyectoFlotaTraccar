# -*- coding: utf-8 -*-
"""
FleetTraccarSync — Modelo de sincronización Traccar ↔ Odoo
==========================================================
Gestiona la descarga y persistencia de posiciones GPS desde Traccar,
actualiza fleet.vehicle y crea registros fleet.posicion.gps.
"""
import json
import logging
import os
from urllib.parse import urlsplit, urlunsplit
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


def traccar_browser_url(configured_url, browser_url, port):
    """
    Una URL pública configurada se usa tal cual. Si está vacía o apunta a un nombre
    local o interno, se usa el servidor con el que el navegador abrió Odoo.
    """
    configured = (configured_url or "").strip().rstrip("/")
    parsed = urlsplit(configured)
    if configured and parsed.hostname not in ("localhost", "127.0.0.1", "::1", "traccar"):
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise UserError("La URL de Traccar debe ser HTTP/HTTPS y no contener credenciales.")
        return configured
    browser = urlsplit(browser_url)
    if not browser.hostname:
        raise UserError("No se pudo determinar el servidor de Odoo.")
    host = f"[{browser.hostname}]" if ":" in browser.hostname else browser.hostname
    published = (parsed.port if parsed.hostname != "traccar" else None) or int(port)
    if not 1 <= published <= 65535:
        raise UserError("Puerto de Traccar inválido.")
    return urlunsplit((browser.scheme, f"{host}:{published}", "", "", ""))


class FleetTraccarSync(models.Model):
    _name = "fleet.traccar.sync"
    _description = "Sincronización Traccar-Odoo"
    _order = "create_date desc"
    _rec_name = "name"

    # ------------------------------------------------------------------
    # Campos
    # ------------------------------------------------------------------

    name = fields.Char(
        string="Referencia",
        compute="_compute_name",
        store=True,
    )
    sync_type = fields.Selection(
        selection=[
            ("ultimo_posicion", "Última Posición"),
            ("historial", "Historial"),
            ("dispositivos", "Dispositivos"),
        ],
        string="Tipo de Sincronización",
        required=True,
        default="ultimo_posicion",
    )
    estado = fields.Selection(
        selection=[
            ("pendiente", "Pendiente"),
            ("en_proceso", "En Proceso"),
            ("completado", "Completado"),
            ("error", "Error"),
        ],
        string="Estado",
        required=True,
        default="pendiente",
        index=True,
    )
    fecha_inicio = fields.Datetime(
        string="Fecha Inicio",
        readonly=True,
    )
    fecha_fin = fields.Datetime(
        string="Fecha Fin",
        readonly=True,
    )
    duracion_segundos = fields.Float(
        string="Duración (s)",
        compute="_compute_duracion",
        store=True,
    )
    registros_procesados = fields.Integer(string="Procesados", default=0)
    registros_nuevos = fields.Integer(string="Nuevos", default=0)
    registros_duplicados = fields.Integer(string="Duplicados", default=0)
    registros_error = fields.Integer(string="Con Error", default=0)
    vehicle_ids = fields.Many2many(
        comodel_name="fleet.vehicle",
        relation="fleet_traccar_sync_vehicle_rel",
        column1="sync_id",
        column2="vehicle_id",
        string="Vehículos",
    )
    log_detalle = fields.Text(string="Log Detallado")
    error_mensaje = fields.Text(string="Mensaje de Error")

    # ------------------------------------------------------------------
    # Campos computados
    # ------------------------------------------------------------------

    @api.depends("sync_type", "create_date")
    def _compute_name(self):
        labels = {
            "ultimo_posicion": "Últ. Posición",
            "historial": "Historial",
            "dispositivos": "Dispositivos",
        }
        for rec in self:
            ts = rec.create_date or fields.Datetime.now()
            label = labels.get(rec.sync_type, "Sync")
            rec.name = f"{label} — {fields.Datetime.to_string(ts)}"

    @api.depends("fecha_inicio", "fecha_fin")
    def _compute_duracion(self):
        for rec in self:
            if rec.fecha_inicio and rec.fecha_fin:
                delta = rec.fecha_fin - rec.fecha_inicio
                rec.duracion_segundos = delta.total_seconds()
            else:
                rec.duracion_segundos = 0.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_traccar_service(self):
        """Instancia TraccarService desde los parámetros de configuración."""
        ICP = self.env["ir.config_parameter"].sudo()
        url = ICP.get_param("fleet_traccar.server_url", "http://traccar:8082")
        user = ICP.get_param("fleet_traccar.user", "")
        password = ICP.get_param("fleet_traccar.password", "")
        if not url or not user.strip() or not password:
            raise UserError(
                'Configure la URL, el usuario y la contraseña de Traccar en Ajustes de Flota antes de sincronizar.'
            )
        from ..services.traccar_service import TraccarService

        return TraccarService(url, user, password)

    def _check_sync_access(self):
        self.check_access_rights('write')

    def _create_sync_log(self, sync_type: str) -> "FleetTraccarSync":
        """Crea y retorna un registro de log de sincronización."""
        return self.sudo().create(
            {
                "sync_type": sync_type,
                "estado": "en_proceso",
                "fecha_inicio": fields.Datetime.now(),
            }
        )

    def _publish_realtime_event(self, event_type: str, payload: dict):
        """Publica una actualización en el bus interno de Odoo para las vistas en vivo."""
        message = dict(payload or {})
        message.update({
            "event": event_type,
            "timestamp": fields.Datetime.now().isoformat(),
        })
        try:
            self.env["bus.bus"].sudo().sendone("fleet_rutas/traccar", message)
        except Exception as exc:  # Bus notifications are supplemental to persisted data
            _logger.debug("No se pudo publicar el evento Traccar en el bus: %s", exc)

    def _finalizar_log(
        self,
        sync_record: "FleetTraccarSync",
        stats: dict,
        error_msg: str = "",
        log_lines: Optional[List[str]] = None,
    ):
        """Actualiza el registro de log con los resultados finales."""
        if error_msg:
            stats['errores'] = max(1, stats.get('errores', 0))
        estado = "error" if error_msg or stats.get('errores', 0) else "completado"
        vals = {
            "estado": estado,
            "fecha_fin": fields.Datetime.now(),
            "registros_procesados": stats.get("procesados", 0),
            "registros_nuevos": stats.get("nuevos", 0),
            "registros_duplicados": stats.get("duplicados", 0),
            "registros_error": stats.get("errores", 0),
        }
        if error_msg:
            vals["error_mensaje"] = error_msg
        if log_lines:
            vals["log_detalle"] = "\n".join(log_lines)
        sync_record.sudo().write(vals)

    @staticmethod
    def _parse_iso_datetime(value: str) -> Optional[datetime]:
        """Parsea ISO 8601 a datetime naive UTC."""
        if not value:
            return None
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(value, fmt)
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                return dt
            except ValueError:
                continue
        return None

    # ------------------------------------------------------------------
    # sincronizar_ultima_posicion
    # ------------------------------------------------------------------

    @api.model
    def sincronizar_ultima_posicion(self, vehicle_ids: Optional[List[int]] = None) -> Dict:
        """
        Sincroniza la última posición GPS desde Traccar.

        Flujo:
        1. Crear registro de log.
        2. Obtener TraccarService.
        3. Obtener vehículos con tracking habilitado.
        4. Llamar get_last_positions().
        5. Para cada posición: dedup, actualizar vehicle, crear posicion.gps.
        6. Ejecutar detectar_desviacion().
        7. Actualizar log.

        :param vehicle_ids: IDs de fleet.vehicle a sincronizar (None = todos).
        :returns: Dict con estadísticas.
        """
        self._check_sync_access()
        from ..services.traccar_service import TraccarAPIError

        sync_log = self._create_sync_log("ultimo_posicion")
        stats = {"procesados": 0, "nuevos": 0, "duplicados": 0, "errores": 0}
        log_lines: List[str] = []

        try:
            svc = self._get_traccar_service()

            # ── Obtener vehículos ────────────────────────────────────────
            domain = [
                ("traccar_tracking_enabled", "=", True),
                ("traccar_device_id", "!=", False),
            ]
            if vehicle_ids:
                domain.append(("id", "in", vehicle_ids))

            vehicles = self.env["fleet.vehicle"].sudo().search(domain)
            sync_log.vehicle_ids = [(6, 0, vehicles.ids)]
            if not vehicles:
                log_lines.append("No hay vehículos con tracking habilitado.")
                self._finalizar_log(sync_log, stats, log_lines=log_lines)
                self._publish_realtime_event("posicion", {
                    "nuevas": stats["nuevos"],
                    "vehiculos": len(vehicles),
                })
                return stats

            device_vehicle_map: Dict[int, object] = {
                v.traccar_device_id: v for v in vehicles
            }
            device_ids_list = list(device_vehicle_map.keys())
            log_lines.append(f"Vehículos a sincronizar: {len(vehicles)}")

            # ── Obtener últimas posiciones ───────────────────────────────
            positions = svc.get_last_positions(device_ids=device_ids_list)
            log_lines.append(f"Posiciones recibidas de Traccar: {len(positions)}")

            if not positions:
                self._finalizar_log(sync_log, stats, log_lines=log_lines)
                self._publish_realtime_event("posicion", {
                    "nuevas": stats["nuevos"],
                    "vehiculos": len(vehicles),
                })
                return stats

            # ── Cargar IDs ya existentes (evita N queries) ───────────────
            incoming_ids = [p["id"] for p in positions if isinstance(p.get("id"), int)]
            existing_ids: set = set()
            if incoming_ids:
                existing_records = (
                    self.env["fleet.posicion.gps"]
                    .sudo()
                    .search([("traccar_position_id", "in", incoming_ids)])
                )
                existing_ids = set(existing_records.mapped("traccar_position_id"))

            # ── Buscar recorridos activos ────────────────────────────────
            active_recorridos = (
                self.env["fleet.recorrido"]
                .sudo()
                .search([("estado", "=", "en_curso")])
            )
            vehicle_recorrido_map: Dict[int, object] = {
                r.vehicle_id.id: r for r in active_recorridos
            }

            # ── Procesar cada posición ───────────────────────────────────
            nuevas_posiciones = []
            for pos in positions:
                try:
                    with self.env.cr.savepoint():
                        result = self._procesar_posicion_ultima(
                            pos=pos, device_vehicle_map=device_vehicle_map,
                            vehicle_recorrido_map=vehicle_recorrido_map,
                            existing_ids=existing_ids, stats=stats,
                        )
                    if result:
                        nuevas_posiciones.append(result)
                except Exception as exc:  # noqa: BLE001
                    stats["errores"] += 1
                    _logger.error(
                        "sincronizar_ultima_posicion: error en pos id=%s — %s",
                        pos.get("id"),
                        exc,
                        exc_info=True,
                    )

            stats["procesados"] = len(positions)
            log_lines.append(
                f"Nuevas: {stats['nuevos']} | Duplicadas: {stats['duplicados']} "
                f"| Errores: {stats['errores']}"
            )

            # ── Detectar desviaciones en nuevas posiciones ───────────────
            for pos_record, recorrido in nuevas_posiciones:
                if recorrido:
                    try:
                        pos_record.detectar_desviacion()
                    except Exception as exc:  # noqa: BLE001
                        _logger.warning(
                            "sincronizar_ultima_posicion: detectar_desviacion falló "
                            "para posicion id=%s — %s",
                            pos_record.id,
                            exc,
                        )

            self._finalizar_log(sync_log, stats, log_lines=log_lines)
            self._publish_realtime_event("posicion", {
                "nuevas": stats["nuevos"],
                "vehiculos": len(vehicles),
            })
            return stats

        except TraccarAPIError as exc:
            error_msg = f"Error de API Traccar: {exc}"
            _logger.error("sincronizar_ultima_posicion: %s", error_msg, exc_info=True)
            self._finalizar_log(sync_log, stats, error_msg=error_msg, log_lines=log_lines)
            return stats
        except Exception as exc:  # noqa: BLE001
            error_msg = f"Error inesperado: {exc}"
            _logger.exception("sincronizar_ultima_posicion: %s", error_msg)
            self._finalizar_log(sync_log, stats, error_msg=error_msg, log_lines=log_lines)
            return stats

    def _procesar_posicion_ultima(
        self,
        pos: dict,
        device_vehicle_map: dict,
        vehicle_recorrido_map: dict,
        existing_ids: set,
        stats: dict,
    ) -> Optional[Tuple]:
        """
        Procesa una posición de get_last_positions.
        Retorna (posicion_record, recorrido) si se creó, None si duplicado/ignorado.
        """
        traccar_pos_id = pos.get("id")
        device_id = pos.get("deviceId")

        if not isinstance(traccar_pos_id, int) or not isinstance(device_id, int):
            return None

        if traccar_pos_id in existing_ids:
            stats["duplicados"] += 1
            return None

        vehicle = device_vehicle_map.get(device_id)
        if not vehicle:
            return None

        latitude = pos.get("latitude")
        longitude = pos.get("longitude")
        if latitude is None or longitude is None:
            return None

        altitude = float(pos.get("altitude", 0.0))
        speed_kmh = float(pos.get("speed", 0.0)) * 1.852
        course = float(pos.get("course", 0.0))
        accuracy = float(pos.get("accuracy", 0.0))
        attributes = pos.get("attributes", {})

        timestamp_str = pos.get("fixTime") or pos.get("deviceTime") or pos.get("serverTime")
        timestamp = self._parse_iso_datetime(timestamp_str)

        if timestamp is None or pos.get("valid") is False:
            raise ValueError("Invalid GPS timestamp or fix")
        if self.env["fleet.posicion.gps"].sudo().buscar_equivalente(
                vehicle.id, timestamp, float(latitude), float(longitude), traccar_pos_id):
            existing_ids.add(traccar_pos_id)
            stats["duplicados"] += 1
            return None
        recorrido = vehicle_recorrido_map.get(vehicle.id)
        if recorrido and recorrido.fecha_inicio_real and timestamp < recorrido.fecha_inicio_real:
            recorrido = None

        # Crear posicion.gps
        pos_record = self.env["fleet.posicion.gps"].sudo().create(
            {
                "payload_origen": json.dumps(pos),
                "traccar_position_id": traccar_pos_id,
                "vehicle_id": vehicle.id,
                "recorrido_id": recorrido.id if recorrido else False,
                "latitud": float(latitude),
                "longitud": float(longitude),
                "altitud": altitude,
                "velocidad": speed_kmh,
                "rumbo": course,
                "precision": accuracy,
                "timestamp": timestamp,
                "atributos_raw": json.dumps(attributes) if attributes else "{}",
            }
        )
        existing_ids.add(traccar_pos_id)
        stats["nuevos"] += 1

        # Actualizar fleet.vehicle
        if not vehicle.traccar_last_update or timestamp >= vehicle.traccar_last_update:
            vehicle.sudo().write(
            {
                "traccar_last_latitude": float(latitude),
                "traccar_last_longitude": float(longitude),
                "traccar_last_speed": speed_kmh,
                "traccar_last_update": timestamp,
            }
        )

        return pos_record, recorrido

    # ------------------------------------------------------------------
    # sincronizar_historial
    # ------------------------------------------------------------------

    @api.model
    def sincronizar_historial(
        self,
        recorrido_id: int,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> Dict:
        """
        Descarga el historial completo de posiciones GPS para un recorrido.

        Flujo:
        1. Cargar recorrido, obtener traccar_device_id del vehículo.
        2. Llamar get_position_history() para la ventana temporal del recorrido.
        3. Filtrar duplicados por traccar_position_id.
        4. Aplicar filtrar_posiciones_duplicadas() para deduplicar por tiempo.
        5. Crear fleet.posicion.gps en lote.
        6. Ejecutar detectar_desviacion() para cada posición.
        7. Actualizar recorrido.distancia_real_km.
        8. Retornar dict con estadísticas.
        """
        self._check_sync_access()
        self.env['fleet.recorrido'].browse(recorrido_id).check_access_rule('write')
        from ..services.traccar_service import TraccarAPIError

        sync_log = self._create_sync_log("historial")
        stats = {"procesados": 0, "nuevos": 0, "duplicados": 0, "errores": 0}
        log_lines: List[str] = []

        try:
            # ── Cargar recorrido ─────────────────────────────────────────
            recorrido = self.env["fleet.recorrido"].sudo().browse(recorrido_id)
            if not recorrido.exists():
                raise UserError(f"Recorrido id={recorrido_id} no encontrado.")

            vehicle = recorrido.vehicle_id
            sync_log.vehicle_ids = [(6, 0, vehicle.ids)]
            if not vehicle or not vehicle.traccar_device_id:
                raise UserError(
                    f"El vehículo del recorrido id={recorrido_id} no tiene "
                    "traccar_device_id configurado."
                )

            device_id = vehicle.traccar_device_id
            log_lines.append(
                f"Recorrido: {recorrido.name} | Vehículo: {vehicle.name} "
                f"| Traccar device_id: {device_id}"
            )

            # ── Rango temporal ───────────────────────────────────────────
            effective_from = from_dt or recorrido.fecha_inicio_real or recorrido.fecha_inicio
            effective_to = to_dt or recorrido.fecha_fin_real or fields.Datetime.now()

            if isinstance(effective_from, str):
                effective_from = fields.Datetime.from_string(effective_from)
            if isinstance(effective_to, str):
                effective_to = fields.Datetime.from_string(effective_to)

            if not effective_from:
                raise UserError("El recorrido no tiene fecha_inicio definida.")

            log_lines.append(
                f"Rango: {effective_from.isoformat()} → {effective_to.isoformat()}"
            )

            # ── Obtener historial desde Traccar ──────────────────────────
            svc = self._get_traccar_service()
            positions = svc.get_position_history(device_id, effective_from, effective_to)
            log_lines.append(f"Posiciones recibidas de Traccar: {len(positions)}")
            stats["procesados"] = len(positions)

            if not positions:
                self._finalizar_log(sync_log, stats, log_lines=log_lines)
                return stats

            # ── Filtrar duplicados ya almacenados ────────────────────────
            incoming_ids = [p["id"] for p in positions if isinstance(p.get("id"), int)]
            existing_ids: set = set()
            if incoming_ids:
                existing_records = (
                    self.env["fleet.posicion.gps"]
                    .sudo()
                    .search(
                        [
                            ("traccar_position_id", "in", incoming_ids),
                        ]
                    )
                )
                existing_ids = set(existing_records.mapped("traccar_position_id"))
                # A last-position poll may have stored this fix before assignment.
                unassigned = existing_records.filtered(lambda p: not p.recorrido_id and p.vehicle_id == vehicle)
                unassigned.write({'recorrido_id': recorrido.id})
                unassigned.detectar_desviacion()

            nuevas_positions = [
                p for p in positions if p.get("id") not in existing_ids
            ]
            stats["duplicados"] = len(positions) - len(nuevas_positions)
            log_lines.append(
                f"Duplicados (ya en BD): {stats['duplicados']} | "
                f"A procesar: {len(nuevas_positions)}"
            )

            # ── Filtrar posiciones duplicadas por timestamp (dedup espacial) ──
            nuevas_positions = self._filtrar_posiciones_duplicadas(nuevas_positions)
            log_lines.append(
                f"Después de filtro temporal: {len(nuevas_positions)} posiciones"
            )

            # ── Inserción en lote usando INSERT directo ──────────────────
            creadas = self._insertar_posiciones_bulk(
                positions=nuevas_positions,
                recorrido=recorrido,
                vehicle=vehicle,
                stats=stats,
            )
            log_lines.append(f"Posiciones nuevas creadas: {stats['nuevos']}")

            # ── Detectar desviaciones ────────────────────────────────────
            for pos_record in creadas:
                try:
                    pos_record.detectar_desviacion()
                except Exception as exc:  # noqa: BLE001
                    _logger.warning(
                        "sincronizar_historial: detectar_desviacion falló "
                        "para posicion id=%s — %s",
                        pos_record.id,
                        exc,
                    )

            # ── Recalcular distancia real del recorrido ──────────────────
            self._actualizar_distancia_recorrido(recorrido)
            log_lines.append("Distancia real del recorrido actualizada.")

            self._finalizar_log(sync_log, stats, log_lines=log_lines)
            return stats

        except (UserError, TraccarAPIError) as exc:
            error_msg = str(exc)
            _logger.error("sincronizar_historial: %s", error_msg, exc_info=True)
            self._finalizar_log(sync_log, stats, error_msg=error_msg, log_lines=log_lines)
            return stats
        except Exception as exc:  # noqa: BLE001
            error_msg = f"Error inesperado: {exc}"
            _logger.exception("sincronizar_historial: %s", error_msg)
            self._finalizar_log(sync_log, stats, error_msg=error_msg, log_lines=log_lines)
            return stats

    @staticmethod
    def _filtrar_posiciones_duplicadas(positions: List[Dict]) -> List[Dict]:
        """Deduplica por ID de origen sin descartar puntos válidos por su hora o ubicación."""
        filtered = []
        seen = set()
        for pos in positions:
            position_id = pos.get('id')
            if position_id is not None and position_id in seen:
                continue
            if position_id is not None:
                seen.add(position_id)
            filtered.append(pos)
        return filtered

    def _insertar_posiciones_bulk(
        self,
        positions: List[Dict],
        recorrido,
        vehicle,
        stats: dict,
    ) -> List:
        """Importa con ORM y savepoint por punto, aislando también errores de conversión."""
        if not positions:
            return []

        records = []
        for pos in positions:
            try:
                timestamp = self._parse_iso_datetime(pos.get('fixTime') or pos.get('deviceTime') or pos.get('serverTime'))
                if timestamp is None or pos.get('valid') is False:
                    raise ValueError('Timestamp o fix GPS inválido')
                if type(pos.get('id')) is not int or pos['id'] <= 0:
                    raise ValueError('ID de posición Traccar inválido')
                attributes = pos.get('attributes', {})
                vals = {
                    "payload_origen": json.dumps(pos),
                    "traccar_position_id": pos.get("id"),
                    "vehicle_id": vehicle.id,
                    "recorrido_id": recorrido.id,
                    "latitud": float(pos['latitude']),
                    "longitud": float(pos['longitude']),
                    "altitud": float(pos.get("altitude", 0.0)),
                    "velocidad": float(pos.get('speed', 0.0)) * 1.852,
                    "rumbo": float(pos.get("course", 0.0)),
                    "precision": float(pos.get("accuracy", 0.0)),
                    "timestamp": timestamp,
                    "atributos_raw": json.dumps(attributes) if attributes else "{}",
                }
                with self.env.cr.savepoint():
                    Posicion = self.env["fleet.posicion.gps"].sudo()
                    previa = Posicion.buscar_equivalente(
                        vehicle.id, timestamp, vals["latitud"], vals["longitud"], pos["id"])
                    if previa:
                        stats["duplicados"] = stats.get("duplicados", 0) + 1
                        if not previa.recorrido_id:
                            previa.write({"recorrido_id": recorrido.id})
                            records.append(previa)  # falta evaluar desvío y paradas
                        continue
                    record = Posicion.create(vals)
                records.append(record)
                stats["nuevos"] += 1
            except Exception:
                stats["errores"] += 1
                _logger.exception('No se pudo importar la posición Traccar %s', pos.get('id'))
        return records

    def _actualizar_distancia_recorrido(self, recorrido):
        """
        Recalcula ``distancia_real_km`` del recorrido sumando la distancia
        Haversine entre posiciones consecutivas.
        """
        from .fleet_algoritmos import calcular_distancia_total_km

        positions = (
            self.env["fleet.posicion.gps"]
            .sudo()
            .search(
                [("recorrido_id", "=", recorrido.id)],
                order="timestamp asc",
            )
        )
        if len(positions) < 2:
            return

        total_km = calcular_distancia_total_km(
            [{"latitud": p.latitud, "longitud": p.longitud} for p in positions])
        recorrido.sudo().write({"distancia_real_km": round(total_km, 3)})

    # ------------------------------------------------------------------
    # sincronizar_dispositivos
    # ------------------------------------------------------------------

    @api.model
    def sincronizar_dispositivos(self) -> Dict:
        """
        Sincroniza el estado de dispositivos Traccar con fleet.vehicle.
        Actualiza ``traccar_device_status`` en cada vehículo.

        :returns: Dict con estadísticas.
        """
        self._check_sync_access()
        from ..services.traccar_service import TraccarAPIError

        sync_log = self._create_sync_log("dispositivos")
        stats = {"procesados": 0, "nuevos": 0, "duplicados": 0, "errores": 0}
        log_lines: List[str] = []

        try:
            svc = self._get_traccar_service()
            devices = svc.get_devices()
            log_lines.append(f"Dispositivos obtenidos de Traccar: {len(devices)}")
            stats["procesados"] = len(devices)

            if not devices:
                self._finalizar_log(sync_log, stats, log_lines=log_lines)
                return stats

            # Incluye archivados: de lo contrario se intentaría crear un duplicado.
            Vehicle = self.env["fleet.vehicle"].sudo().with_context(active_test=False)
            created = 0
            updated = 0

            for device in devices:
                d_id = device.get("id")
                unique_id = (device.get("uniqueId") or "").strip()
                name = (device.get("name") or "").strip()
                status = str(device.get("status") or "unknown").lower()
                if not isinstance(d_id, int):
                    stats["errores"] += 1
                    continue

                vehicle = Vehicle.search([("traccar_device_id", "=", d_id)], limit=1)
                if not vehicle and unique_id:
                    vehicle = Vehicle.search([("traccar_unique_id", "=", unique_id)], limit=1)

                try:
                    if not vehicle:
                        Brand = self.env["fleet.vehicle.model.brand"].sudo()
                        Model = self.env["fleet.vehicle.model"].sudo()
                        brand = Brand.search([("name", "=", "Traccar")], limit=1)
                        if not brand:
                            brand = Brand.create({"name": "Traccar"})
                        model = Model.search([
                            ("name", "=", "Dispositivo GPS automático"),
                            ("brand_id", "=", brand.id),
                        ], limit=1)
                        if not model:
                            model = Model.create({
                                "name": "Dispositivo GPS automático",
                                "brand_id": brand.id,
                                "vehicle_type": "car",
                            })
                        vehicle = Vehicle.create({
                            "model_id": model.id,
                            "license_plate": name or unique_id or f"TR-{d_id}",
                            "traccar_device_name": name or False,
                            "traccar_tracking_enabled": True,
                            "traccar_device_id": d_id,
                            "traccar_unique_id": unique_id or False,
                            "traccar_device_status": status,
                        })
                        created += 1
                        _logger.info(
                            "sincronizar_dispositivos: vehículo creado para Traccar ID %d (%s).",
                            d_id, name or unique_id,
                        )
                    else:
                        vals = {
                            "traccar_device_id": d_id,
                            "traccar_unique_id": unique_id or vehicle.traccar_unique_id,
                            "traccar_device_name": name or vehicle.traccar_device_name,
                            "traccar_device_status": status,
                        }
                        # Solo se activa al vincular por primera vez: se respeta
                        # el seguimiento que el administrador haya desactivado.
                        if not vehicle.traccar_device_id:
                            vals["traccar_tracking_enabled"] = True
                        changed = any(vehicle[field] != value for field, value in vals.items())
                        if changed:
                            vehicle.write(vals)
                        updated += 1
                        _logger.debug(
                            "sincronizar_dispositivos: vehículo id=%d "
                            "actualizado desde Traccar.",
                            vehicle.id,
                        )
                except Exception as exc:  # noqa: BLE001
                    stats["errores"] += 1
                    _logger.error(
                        "sincronizar_dispositivos: error procesando "
                        "dispositivo id=%r — %s",
                        d_id, exc,
                    )

            # Se señalan, sin borrarlos, los vehículos cuyo dispositivo ya no aparece.
            # Una lista vacía sale antes: sin datos no se marca nada.
            presentes = [d["id"] for d in devices if isinstance(d.get("id"), int)]
            ausentes = Vehicle.search([
                ("traccar_tracking_enabled", "=", True),
                ("traccar_device_id", ">", 0),
                ("traccar_device_id", "not in", presentes),
                ("traccar_device_status", "!=", "removed"),
            ])
            if ausentes:
                ausentes.write({"traccar_device_status": "removed"})
                log_lines.append(f"Vehículos sin dispositivo en Traccar: {len(ausentes)}")

            stats["nuevos"] = created
            log_lines.append(
                f"Vehículos creados: {created} | Vehículos actualizados: {updated} "
                f"| Errores: {stats['errores']}"
            )
            self._finalizar_log(sync_log, stats, log_lines=log_lines)
            self._publish_realtime_event("dispositivos", {
                "created": created,
                "updated": updated,
            })
            return stats

        except TraccarAPIError as exc:
            error_msg = f"Error de API Traccar: {exc}"
            _logger.error("sincronizar_dispositivos: %s", error_msg, exc_info=True)
            self._finalizar_log(sync_log, stats, error_msg=error_msg, log_lines=log_lines)
            return stats
        except Exception as exc:  # noqa: BLE001
            error_msg = f"Error inesperado: {exc}"
            _logger.exception("sincronizar_dispositivos: %s", error_msg)
            self._finalizar_log(sync_log, stats, error_msg=error_msg, log_lines=log_lines)
            return stats

    @api.model
    def get_traccar_web_url(self):
        """Dirección de la web de Traccar tal como debe abrirla el navegador."""
        self._check_sync_access()
        return traccar_browser_url(
            self.env["ir.config_parameter"].sudo().get_param("fleet_traccar.public_url", ""),
            request.httprequest.host_url,
            os.environ.get("TRACCAR_WEB_PORT", "8082"),
        )

    # ------------------------------------------------------------------
    # verificar_perdida_senal
    # ------------------------------------------------------------------

    @api.model
    def verificar_perdida_senal(self, recorrido_id: int, ahora=None) -> int:
        """
        Analiza el historial GPS del recorrido en busca de pérdida de señal.
        Crea fleet.incidencia de tipo 'senal_perdida' si detecta brechas > 2 min.

        :param recorrido_id: ID del recorrido a analizar.
        :returns: Número de incidencias creadas.
        """
        GAP_THRESHOLD_MINUTES = 2
        incidencias_creadas = 0

        recorrido = self.env["fleet.recorrido"].sudo().browse(recorrido_id)
        if not recorrido.exists():
            _logger.warning(
                "verificar_perdida_senal: recorrido id=%d no encontrado.", recorrido_id
            )
            return 0

        positions = (
            self.env["fleet.posicion.gps"]
            .sudo()
            .search(
                [("recorrido_id", "=", recorrido_id)],
                order="timestamp asc",
            )
        )

        if recorrido.fecha_inicio_real:
            end = recorrido.fecha_fin_real or ahora or fields.Datetime.now()
            last = positions[-1].timestamp if positions else recorrido.fecha_inicio_real
            if (end - last).total_seconds() > 120:
                incidence = self.env['fleet.incidencia'].sudo()
                if not incidence.search_count([('recorrido_id', '=', recorrido_id), ('tipo', '=', 'senal_perdida'), ('timestamp', '=', last)]):
                    incidence.crear_incidencia_perdida_senal(recorrido_id, (end - last).total_seconds(), last)
                    incidencias_creadas += 1
        if len(positions) < 2:
            return incidencias_creadas

        Incidencia = self.env["fleet.incidencia"].sudo()

        prev = positions[0]
        for curr in positions[1:]:
            if not prev.timestamp or not curr.timestamp:
                prev = curr
                continue

            gap_seconds = (curr.timestamp - prev.timestamp).total_seconds()
            gap_minutes = gap_seconds / 60.0

            if gap_minutes > GAP_THRESHOLD_MINUTES:
                # Verificar que no existe ya una incidencia para este gap
                existing = Incidencia.search(
                    [
                        ("recorrido_id", "=", recorrido_id),
                        ("tipo", "=", "senal_perdida"),
                        ("timestamp", "=", prev.timestamp),
                    ],
                    limit=1,
                )
                if not existing:
                    try:
                        Incidencia.crear_incidencia_perdida_senal(
                            recorrido_id=recorrido_id,
                            duracion_seg=gap_seconds,
                            timestamp_inicio=prev.timestamp,
                        )
                        incidencias_creadas += 1
                        _logger.info(
                            "verificar_perdida_senal: brecha de %.1f min detectada "
                            "en recorrido id=%d.",
                            gap_minutes,
                            recorrido_id,
                        )
                    except Exception as exc:  # noqa: BLE001
                        _logger.error(
                            "verificar_perdida_senal: error creando incidencia — %s", exc
                        )

            prev = curr

        return incidencias_creadas

    @api.model
    def monitorear_perdida_senal_activos(self) -> int:
        """
        Monitorea la pérdida de señal en todos los recorridos activos (en_curso).
        Invocado periódicamente por la acción programada ir_cron_detect_signal_loss.
        """
        recorridos = self.env["fleet.recorrido"].sudo().search([("estado", "=", "en_curso")])
        total_incidencias = 0
        for rec in recorridos:
            total_incidencias += self.verificar_perdida_senal(rec.id)
        return total_incidencias

    # ------------------------------------------------------------------
    # action_ejecutar_sync (botón de UI)
    # ------------------------------------------------------------------

    def action_ejecutar_sync(self):
        """
        Acción de botón para ejecutar manualmente la sincronización
        según el tipo configurado en el registro.
        """
        self.ensure_one()
        sync_type = self.sync_type

        if sync_type == "ultimo_posicion":
            vehicle_ids = self.vehicle_ids.ids or None
            result = self.sincronizar_ultima_posicion(vehicle_ids=vehicle_ids)

        elif sync_type == "dispositivos":
            result = self.sincronizar_dispositivos()

        elif sync_type == "historial":
            raise UserError(
                "Para sincronizar historial, use la acción desde el recorrido correspondiente."
            )
        else:
            raise UserError(f"Tipo de sincronización desconocido: {sync_type!r}")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Sincronización completada",
                "message": (
                    f"Nuevos: {result.get('nuevos', 0)} | "
                    f"Duplicados: {result.get('duplicados', 0)} | "
                    f"Errores: {result.get('errores', 0)}"
                ),
                "type": "success" if not result.get("errores") else "warning",
                "sticky": False,
            },
        }

# -*- coding: utf-8 -*-
"""
FleetTraccarSync — Modelo de sincronización Traccar ↔ Odoo
==========================================================
Gestiona la descarga y persistencia de posiciones GPS desde Traccar,
actualiza fleet.vehicle y crea registros fleet.posicion.gps.
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


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
        from ..services.traccar_service import TraccarService

        return TraccarService(url, user, password)

    def _create_sync_log(self, sync_type: str) -> "FleetTraccarSync":
        """Crea y retorna un registro de log de sincronización."""
        return self.sudo().create(
            {
                "sync_type": sync_type,
                "estado": "en_proceso",
                "fecha_inicio": fields.Datetime.now(),
            }
        )

    def _finalizar_log(
        self,
        sync_record: "FleetTraccarSync",
        stats: dict,
        error_msg: str = "",
        log_lines: Optional[List[str]] = None,
    ):
        """Actualiza el registro de log con los resultados finales."""
        estado = "error" if error_msg else "completado"
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
            if not vehicles:
                log_lines.append("No hay vehículos con tracking habilitado.")
                self._finalizar_log(sync_log, stats, log_lines=log_lines)
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
                    result = self._procesar_posicion_ultima(
                        pos=pos,
                        device_vehicle_map=device_vehicle_map,
                        vehicle_recorrido_map=vehicle_recorrido_map,
                        existing_ids=existing_ids,
                        stats=stats,
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

        recorrido = vehicle_recorrido_map.get(vehicle.id)

        # Crear posicion.gps
        pos_record = self.env["fleet.posicion.gps"].sudo().create(
            {
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
            effective_from = from_dt or recorrido.fecha_inicio
            effective_to = to_dt or recorrido.fecha_fin or fields.Datetime.now()

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
                            ("recorrido_id", "=", recorrido_id),
                        ]
                    )
                )
                existing_ids = set(existing_records.mapped("traccar_position_id"))

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
        """
        Elimina posiciones con timestamp idéntico o diferencia < 1 segundo
        (duplicados de GPS) conservando la más reciente.

        También elimina posiciones con (lat, lon) = (0.0, 0.0) que indican
        fallo de señal.

        :param positions: Lista ordenada cronológicamente.
        :returns: Lista filtrada.
        """
        filtered = []
        last_ts: Optional[str] = None

        for pos in positions:
            lat = pos.get("latitude", 0.0)
            lon = pos.get("longitude", 0.0)

            # Ignorar coordenadas nulas (señal perdida)
            if lat == 0.0 and lon == 0.0:
                continue

            ts = pos.get("fixTime") or pos.get("deviceTime") or ""
            if ts == last_ts:
                # Mismo timestamp exacto — reemplazar el anterior
                if filtered:
                    filtered[-1] = pos
                continue

            filtered.append(pos)
            last_ts = ts

        return filtered

    def _insertar_posiciones_bulk(
        self,
        positions: List[Dict],
        recorrido,
        vehicle,
        stats: dict,
    ) -> List:
        """
        Inserta posiciones en lote usando ORM de Odoo (compatible con
        cualquier backend). Para volúmenes > 1000 registros usa
        ``self.env.cr.execute()`` con un INSERT múltiple para mayor rendimiento.

        :returns: Recordset de posiciones creadas.
        """
        if not positions:
            return []

        # Para lotes grandes: INSERT directo + búsqueda posterior
        BULK_THRESHOLD = 500

        vals_list = []
        for pos in positions:
            lat = pos.get("latitude")
            lon = pos.get("longitude")
            if lat is None or lon is None:
                stats["errores"] += 1
                continue

            timestamp_str = (
                pos.get("fixTime") or pos.get("deviceTime") or pos.get("serverTime")
            )
            timestamp = self._parse_iso_datetime(timestamp_str)
            speed_kmh = float(pos.get("speed", 0.0)) * 1.852
            attributes = pos.get("attributes", {})

            vals_list.append(
                {
                    "traccar_position_id": pos.get("id"),
                    "vehicle_id": vehicle.id,
                    "recorrido_id": recorrido.id,
                    "latitud": float(lat),
                    "longitud": float(lon),
                    "altitud": float(pos.get("altitude", 0.0)),
                    "velocidad": speed_kmh,
                    "rumbo": float(pos.get("course", 0.0)),
                    "precision": float(pos.get("accuracy", 0.0)),
                    "timestamp": timestamp,
                    "atributos_raw": json.dumps(attributes) if attributes else "{}",
                }
            )

        if not vals_list:
            return []

        if len(vals_list) >= BULK_THRESHOLD:
            return self._insertar_bulk_sql(vals_list, stats)
        else:
            PosicionGps = self.env["fleet.posicion.gps"].sudo()
            records = PosicionGps.create(vals_list)
            stats["nuevos"] += len(records)
            return list(records)

    def _insertar_bulk_sql(self, vals_list: List[Dict], stats: dict) -> List:
        """
        Inserta posiciones directamente con SQL para máximo rendimiento.
        Retorna los registros recién creados como lista de browse records.
        """
        cr = self.env.cr
        now = fields.Datetime.to_string(fields.Datetime.now())

        rows = []
        for vals in vals_list:
            ts = (
                fields.Datetime.to_string(vals["timestamp"])
                if vals.get("timestamp")
                else now
            )
            rows.append(
                (
                    vals.get("traccar_position_id"),
                    vals["vehicle_id"],
                    vals["recorrido_id"],
                    vals["latitud"],
                    vals["longitud"],
                    vals.get("altitud", 0.0),
                    vals.get("velocidad", 0.0),
                    vals.get("rumbo", 0.0),
                    vals.get("precision", 0.0),
                    ts,
                    vals.get("atributos_raw", "{}"),
                    now,  # create_date
                    now,  # write_date
                    self.env.uid,  # create_uid
                    self.env.uid,  # write_uid
                )
            )

        # Construir INSERT múltiple con parámetros (seguro contra SQL injection)
        placeholders = ", ".join(
            ["(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(rows)
        )
        flat_values = [v for row in rows for v in row]

        cr.execute(
            f"""
            INSERT INTO fleet_posicion_gps
              (traccar_position_id, vehicle_id, recorrido_id,
               latitud, longitud, altitud, velocidad, rumbo, precision,
               timestamp, atributos_raw,
               create_date, write_date, create_uid, write_uid)
            VALUES {placeholders}
            RETURNING id
            """,
            flat_values,
        )
        inserted_ids = [row[0] for row in cr.fetchall()]
        stats["nuevos"] += len(inserted_ids)

        # Invalidar caché del ORM
        self.env["fleet.posicion.gps"].invalidate_model()

        return list(
            self.env["fleet.posicion.gps"].sudo().browse(inserted_ids)
        )

    def _actualizar_distancia_recorrido(self, recorrido):
        """
        Recalcula ``distancia_real_km`` del recorrido sumando la distancia
        Haversine entre posiciones consecutivas.
        """
        import math

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

        R = 6371.0  # Radio de la Tierra en km

        def haversine(lat1, lon1, lat2, lon2):
            phi1, phi2 = math.radians(lat1), math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlambda = math.radians(lon2 - lon1)
            a = (
                math.sin(dphi / 2) ** 2
                + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
            )
            return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        total_km = 0.0
        prev = positions[0]
        for curr in positions[1:]:
            total_km += haversine(
                prev.latitud, prev.longitud, curr.latitud, curr.longitud
            )
            prev = curr

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

            # Mapear device_id → status desde Traccar
            device_status_map: Dict[int, str] = {}
            for device in devices:
                d_id = device.get("id")
                status = device.get("status", "unknown").lower()
                if isinstance(d_id, int):
                    device_status_map[d_id] = status

            # Obtener vehículos con traccar_device_id
            vehicles = (
                self.env["fleet.vehicle"]
                .sudo()
                .search([("traccar_device_id", "!=", False)])
            )

            updated = 0
            for vehicle in vehicles:
                d_id = vehicle.traccar_device_id
                new_status = device_status_map.get(d_id, "unknown")
                current_status = vehicle.traccar_device_status or "unknown"

                if new_status != current_status:
                    try:
                        vehicle.sudo().write({"traccar_device_status": new_status})
                        updated += 1
                        _logger.debug(
                            "sincronizar_dispositivos: vehículo id=%d "
                            "status %s → %s",
                            vehicle.id,
                            current_status,
                            new_status,
                        )
                    except Exception as exc:  # noqa: BLE001
                        stats["errores"] += 1
                        _logger.error(
                            "sincronizar_dispositivos: error actualizando "
                            "vehículo id=%d — %s",
                            vehicle.id,
                            exc,
                        )

            stats["nuevos"] = updated
            log_lines.append(
                f"Vehículos actualizados: {updated} | Errores: {stats['errores']}"
            )
            self._finalizar_log(sync_log, stats, log_lines=log_lines)
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

    # ------------------------------------------------------------------
    # verificar_perdida_senal
    # ------------------------------------------------------------------

    @api.model
    def verificar_perdida_senal(self, recorrido_id: int) -> int:
        """
        Analiza el historial GPS del recorrido en busca de pérdida de señal.
        Crea fleet.incidencia de tipo 'senal_perdida' si detecta brechas > 2 min.

        :param recorrido_id: ID del recorrido a analizar.
        :returns: Número de incidencias creadas.
        """
        GAP_THRESHOLD_MINUTES = 2

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

        if len(positions) < 2:
            return 0

        incidencias_creadas = 0
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

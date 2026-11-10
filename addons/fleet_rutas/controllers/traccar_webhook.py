# -*- coding: utf-8 -*-
"""
Traccar Webhook Controller
==========================
Recibe actualizaciones de posición GPS desde Traccar mediante HTTP POST,
valida el token secreto, persiste las posiciones en fleet.posicion.gps,
y actualiza los campos de última posición en fleet.vehicle.
"""
import json
import logging
import hmac
import hashlib

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class TraccarWebhookController(http.Controller):
    """Controlador HTTP para el webhook de Traccar."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_webhook_secret(self):
        """Recupera el secreto configurado en ir.config_parameter."""
        return (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("fleet_rutas.webhook_secret", "")
        )

    def _validate_secret(self, req_secret: str) -> bool:
        """
        Compara el token enviado con el secreto almacenado usando
        comparación de tiempo constante para evitar timing-attacks.
        """
        stored = self._get_webhook_secret()
        if not stored or not req_secret:
            return False
        return hmac.compare_digest(stored.strip(), req_secret.strip())

    # ------------------------------------------------------------------
    # Endpoint principal
    # ------------------------------------------------------------------

    @http.route(
        "/fleet_rutas/webhook/traccar",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def receive_traccar_positions(self, **kwargs):
        """
        Recibe el payload JSON de Traccar con posiciones GPS y las persiste en Odoo.

        Autenticación: token enviado en el header ``X-Traccar-Secret`` o como
        parámetro de query ``secret``.

        Respuesta exitosa::

            {"status": "ok", "processed": N}

        Respuesta de error::

            {"status": "error", "message": "..."}
        """
        # ── Autenticación ───────────────────────────────────────────────
        incoming_secret = (
            request.httprequest.headers.get("X-Traccar-Secret", "")
            or request.httprequest.args.get("secret", "")
        )
        if not self._validate_secret(incoming_secret):
            _logger.warning(
                "Webhook Traccar rechazado: token inválido. IP=%s",
                request.httprequest.remote_addr,
            )
            return self._json_response(
                {"status": "error", "message": "Unauthorized"}, status=401
            )

        # ── Parsear cuerpo ──────────────────────────────────────────────
        try:
            raw_body = request.httprequest.data
            if not raw_body:
                return self._json_response(
                    {"status": "error", "message": "Empty body"}, status=400
                )
            payload = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            _logger.exception("Webhook Traccar: error al parsear JSON — %s", exc)
            return self._json_response(
                {"status": "error", "message": "Invalid JSON"}, status=400
            )

        if not isinstance(payload, dict):
            return self._json_response({"status": "error", "message": "Expected JSON object"}, status=400)
        positions = payload.get("positions", [payload["position"]] if "position" in payload else [])
        if not isinstance(positions, list) or any(not isinstance(p, dict) for p in positions):
            return self._json_response(
                {"status": "error", "message": "Invalid payload: 'positions' must be a list"},
                status=400,
            )

        if not positions:
            return self._json_response({"status": "ok", "processed": 0})

        # ── Procesar posiciones ─────────────────────────────────────────
        try:
            processed = self._process_positions(positions)
        except Exception as exc:
            _logger.exception("Webhook Traccar: error inesperado procesando posiciones — %s", exc)
            return self._json_response(
                {"status": "error", "message": "Internal server error"}, status=500
            )

        return self._json_response({"status": "ok", "processed": processed})

    # ------------------------------------------------------------------
    # Lógica de procesamiento
    # ------------------------------------------------------------------

    def _process_positions(self, positions: list) -> int:
        """
        Itera las posiciones del payload, evita duplicados por
        ``traccar_position_id``, crea ``fleet.posicion.gps`` y actualiza
        ``fleet.vehicle``.

        :param positions: Lista de dicts tal como llegan de Traccar.
        :returns: Número de registros efectivamente procesados (no duplicados).
        """
        import odoo
        env = request.env(user=odoo.SUPERUSER_ID)

        PosicionGps = env["fleet.posicion.gps"].sudo()
        Vehicle = env["fleet.vehicle"].sudo()
        Recorrido = env["fleet.recorrido"].sudo()

        # Pre-cargar los traccar_position_id ya existentes para la sesión
        # (evita N consultas individuales para duplicados)
        incoming_pos_ids = [
            p["id"] for p in positions if isinstance(p.get("id"), int)
        ]
        existing_pos_ids = set()
        if incoming_pos_ids:
            existing_records = PosicionGps.search(
                [("traccar_position_id", "in", incoming_pos_ids)],
                order="id asc",
            )
            existing_pos_ids = set(existing_records.mapped("traccar_position_id"))

        # Mapear device_id → vehicle (solo los que tienen tracking habilitado)
        vehicles_with_traccar = Vehicle.search(
            [("traccar_tracking_enabled", "=", True), ("traccar_device_id", "!=", False)]
        )
        device_vehicle_map = {v.traccar_device_id: v for v in vehicles_with_traccar}

        processed = 0

        for pos in positions:
            try:
                with env.cr.savepoint():
                    processed += self._process_single_position(
                        env=env, PosicionGps=PosicionGps, Recorrido=Recorrido,
                        device_vehicle_map=device_vehicle_map,
                        existing_pos_ids=existing_pos_ids, pos=pos,
                    )
            except Exception as exc:  # noqa: BLE001
                _logger.error(
                    "Webhook Traccar: error procesando posición id=%s — %s",
                    pos.get("id"),
                    exc,
                    exc_info=True,
                )
                # Continuar con las demás posiciones
                continue

        return processed

    def _process_single_position(
        self,
        env,
        PosicionGps,
        Recorrido,
        device_vehicle_map: dict,
        existing_pos_ids: set,
        pos: dict,
    ) -> int:
        """
        Procesa una única posición de Traccar.

        :returns: 1 si se creó el registro, 0 si era duplicado o no aplica.
        """
        traccar_position_id = pos.get("id")
        device_id = pos.get("deviceId")

        # Ignorar posiciones sin id o sin device
        if not isinstance(traccar_position_id, int) or not isinstance(device_id, int):
            _logger.debug(
                "Webhook Traccar: posición ignorada (sin id o deviceId válido): %s", pos
            )
            return 0

        # ── Duplicado ───────────────────────────────────────────────────
        if traccar_position_id in existing_pos_ids:
            _logger.debug(
                "Webhook Traccar: posición duplicada traccar_position_id=%s, omitiendo.",
                traccar_position_id,
            )
            return 0

        # ── Vehículo ────────────────────────────────────────────────────
        vehicle = device_vehicle_map.get(device_id)
        if not vehicle:
            _logger.debug(
                "Webhook Traccar: no se encontró vehículo con traccar_device_id=%s.", device_id
            )
            return 0

        # ── Extraer campos ──────────────────────────────────────────────
        latitude = pos.get("latitude")
        longitude = pos.get("longitude")
        altitude = pos.get("altitude", 0.0)
        speed_knots = pos.get("speed", 0.0)
        course = pos.get("course", 0.0)
        accuracy = pos.get("accuracy", 0.0)
        attributes = pos.get("attributes", {})

        # Velocidad: Traccar usa nudos; convertir a km/h
        speed_kmh = float(speed_knots) * 1.852 if speed_knots else 0.0

        # Timestamp: preferir fixTime, luego deviceTime, luego serverTime
        timestamp_str = pos.get("fixTime") or pos.get("deviceTime") or pos.get("serverTime")
        timestamp = self._parse_iso_datetime(timestamp_str)

        if latitude is None or longitude is None or timestamp is None or pos.get("valid") is False:
            _logger.warning(
                "Webhook Traccar: posición id=%s sin lat/lon, omitida.", traccar_position_id
            )
            return 0

        # ── Buscar recorrido activo ─────────────────────────────────────
        recorrido = Recorrido.search(
            [
                ("vehicle_id", "=", vehicle.id),
                ("estado", "=", "en_curso"),
                ("fecha_inicio_real", "<=", timestamp),
            ],
            limit=1,
            order="fecha_inicio desc",
        )

        # ── Crear fleet.posicion.gps ────────────────────────────────────
        vals_posicion = {
            "payload_origen": json.dumps(pos),
            "traccar_position_id": traccar_position_id,
            "vehicle_id": vehicle.id,
            "recorrido_id": recorrido.id if recorrido else False,
            "latitud": float(latitude),
            "longitud": float(longitude),
            "altitud": float(altitude),
            "velocidad": speed_kmh,
            "rumbo": float(course),
            "precision": float(accuracy),
            "timestamp": timestamp,
            "atributos_raw": json.dumps(attributes) if attributes else "{}",
        }
        new_pos = PosicionGps.create(vals_posicion)
        existing_pos_ids.add(traccar_position_id)

        # ── Actualizar última posición en fleet.vehicle ─────────────────
        if not vehicle.traccar_last_update or timestamp >= vehicle.traccar_last_update:
            vehicle.write(
            {
                "traccar_last_latitude": float(latitude),
                "traccar_last_longitude": float(longitude),
                "traccar_last_speed": speed_kmh,
                "traccar_last_update": timestamp,
            }
        )

        # ── Detección de desviación (si hay recorrido activo) ───────────
        if recorrido:
            try:
                new_pos.detectar_desviacion()
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "Webhook Traccar: error en detectar_desviacion para posicion id=%s — %s",
                    new_pos.id,
                    exc,
                )

        _logger.debug(
            "Webhook Traccar: posición id=%s procesada para vehículo id=%s.",
            traccar_position_id,
            vehicle.id,
        )
        return 1

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_iso_datetime(value: str):
        """
        Parsea una cadena ISO 8601 a datetime naive UTC.
        Devuelve None si el valor es inválido.
        """
        if not value:
            return None
        from datetime import datetime, timezone

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
        _logger.warning("Webhook Traccar: no se pudo parsear timestamp '%s'", value)
        return None

    @staticmethod
    def _json_response(data: dict, status: int = 200) -> Response:
        """Construye una respuesta HTTP con Content-Type application/json."""
        body = json.dumps(data)
        return Response(
            body,
            status=status,
            headers=[
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(body.encode("utf-8")))),
            ],
        )

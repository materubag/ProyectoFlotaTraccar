# -*- coding: utf-8 -*-
"""
TraccarService
==============
Cliente Python para la API REST de Traccar.
Gestiona la conexión, autenticación, manejo de errores y reintentos.

No es un modelo Odoo — puede instanciarse libremente desde cualquier contexto.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
from urllib3.util.retry import Retry

_logger = logging.getLogger(__name__)

# Códigos HTTP que no se deben reintentar (errores del cliente)
_CLIENT_ERROR_CODES = {400, 401, 403, 404, 405, 422}

# Códigos que implican rate-limiting o servidor no disponible
_RETRY_STATUS_CODES = [500, 502, 503, 504]


class TraccarAPIError(Exception):
    """Excepción base para errores de la API de Traccar."""

    def __init__(self, message: str, status_code: int = 0, url: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.url = url


class TraccarAuthError(TraccarAPIError):
    """Error de autenticación (401/403)."""


class TraccarNotFoundError(TraccarAPIError):
    """Recurso no encontrado (404)."""


class TraccarRateLimitError(TraccarAPIError):
    """Límite de peticiones excedido (429)."""


class TraccarService:
    """
    Cliente Python para la API REST de Traccar.

    Uso::

        svc = TraccarService("http://traccar:8082", "admin", "admin")
        ok, msg = svc.test_connection()
        if ok:
            devices = svc.get_devices()
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth = HTTPBasicAuth(username, password)
        self.timeout = timeout
        self.session = self._build_session()

    # ------------------------------------------------------------------
    # Construcción de sesión
    # ------------------------------------------------------------------

    def _build_session(self) -> requests.Session:
        """Session con reintentos automáticos y backoff exponencial."""
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=_RETRY_STATUS_CODES,
            allowed_methods=["GET", "POST", "DELETE"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.auth = self.auth
        session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        return session

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        """Construye la URL completa para un endpoint de la API."""
        return f"{self.base_url}/api/{path.lstrip('/')}"

    def _raise_for_status(self, response: requests.Response) -> None:
        """
        Lanza la excepción semántica adecuada según el código HTTP.
        """
        code = response.status_code
        url = response.url

        if code == 401:
            raise TraccarAuthError(
                f"Autenticación fallida para {url}. "
                "Verifique fleet_traccar.user y fleet_traccar.password.",
                status_code=code,
                url=url,
            )
        if code == 403:
            raise TraccarAuthError(
                f"Acceso denegado a {url}.",
                status_code=code,
                url=url,
            )
        if code == 404:
            raise TraccarNotFoundError(
                f"Recurso no encontrado: {url}",
                status_code=code,
                url=url,
            )
        if code == 429:
            raise TraccarRateLimitError(
                f"Rate limit excedido en {url}.",
                status_code=code,
                url=url,
            )
        if code >= 500:
            raise TraccarAPIError(
                f"Error del servidor Traccar ({code}) en {url}: {response.text[:200]}",
                status_code=code,
                url=url,
            )
        if code >= 400:
            raise TraccarAPIError(
                f"Error de cliente ({code}) en {url}: {response.text[:200]}",
                status_code=code,
                url=url,
            )

    def _get(self, path: str, params: Optional[dict] = None) -> object:
        """
        Realiza GET a la API y retorna el JSON decodificado.
        Lanza TraccarAPIError (o subclases) ante cualquier error.
        """
        url = self._url(path)
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            self._raise_for_status(response)
            return response.json()
        except (TraccarAPIError, TraccarAuthError, TraccarNotFoundError, TraccarRateLimitError):
            raise
        except requests.exceptions.ConnectionError as exc:
            raise TraccarAPIError(
                f"No se pudo conectar a Traccar ({url}): {exc}"
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise TraccarAPIError(
                f"Timeout al conectar con Traccar ({url}) tras {self.timeout}s."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise TraccarAPIError(
                f"Error de red al llamar a Traccar ({url}): {exc}"
            ) from exc

    def _post(self, path: str, data: dict) -> object:
        """
        Realiza POST a la API y retorna el JSON decodificado.
        """
        import json as _json

        url = self._url(path)
        try:
            response = self.session.post(
                url, data=_json.dumps(data), timeout=self.timeout
            )
            self._raise_for_status(response)
            return response.json()
        except (TraccarAPIError, TraccarAuthError, TraccarNotFoundError, TraccarRateLimitError):
            raise
        except requests.exceptions.ConnectionError as exc:
            raise TraccarAPIError(
                f"No se pudo conectar a Traccar ({url}): {exc}"
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise TraccarAPIError(
                f"Timeout al conectar con Traccar ({url}) tras {self.timeout}s."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise TraccarAPIError(
                f"Error de red al llamar a Traccar ({url}): {exc}"
            ) from exc

    @staticmethod
    def _to_iso8601(dt: datetime) -> str:
        """
        Convierte un datetime (naive UTC o aware) a ISO 8601 con zona UTC
        en el formato que Traccar espera: ``2024-01-01T10:00:00.000Z``.
        """
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def test_connection(self) -> Tuple[bool, str]:
        """
        Verifica la conectividad con el servidor Traccar.

        :returns: Tupla ``(True, descripción)`` si OK, ``(False, mensaje_error)`` si falla.
        """
        try:
            data = self._get("server")
            version = data.get("version", "desconocida") if isinstance(data, dict) else "?"
            msg = f"Conexión exitosa. Traccar versión: {version}"
            _logger.info("TraccarService.test_connection: %s", msg)
            return True, msg
        except TraccarAuthError as exc:
            _logger.error("TraccarService.test_connection: error de autenticación — %s", exc)
            return False, str(exc)
        except TraccarAPIError as exc:
            _logger.error("TraccarService.test_connection: error de API — %s", exc)
            return False, str(exc)

    def get_devices(self) -> List[Dict]:
        """
        GET /api/devices

        Retorna la lista completa de dispositivos registrados en Traccar.

        :returns: Lista de dicts con la estructura de cada dispositivo.
        :raises TraccarAPIError: Ante cualquier error de comunicación o HTTP.
        """
        try:
            result = self._get("devices")
            if not isinstance(result, list):
                _logger.warning(
                    "TraccarService.get_devices: respuesta inesperada (no es lista): %s",
                    type(result),
                )
                return []
            _logger.info("TraccarService.get_devices: %d dispositivos obtenidos.", len(result))
            return result
        except TraccarAPIError:
            _logger.exception("TraccarService.get_devices: fallo al obtener dispositivos.")
            raise

    def get_device_by_unique_id(self, unique_id: str) -> Optional[Dict]:
        """
        GET /api/devices?uniqueId=X

        Busca un dispositivo por su identificador único (p.ej. IMEI).

        :param unique_id: Identificador único del dispositivo.
        :returns: Dict del dispositivo o None si no existe.
        :raises TraccarAPIError: Ante errores de comunicación o HTTP (excepto 404).
        """
        if not unique_id:
            raise ValueError("unique_id no puede estar vacío.")
        try:
            result = self._get("devices", params={"uniqueId": unique_id})
            if isinstance(result, list):
                return result[0] if result else None
            return result if result else None
        except TraccarNotFoundError:
            _logger.info(
                "TraccarService.get_device_by_unique_id: dispositivo '%s' no encontrado.",
                unique_id,
            )
            return None
        except TraccarAPIError:
            _logger.exception(
                "TraccarService.get_device_by_unique_id: fallo para unique_id='%s'.", unique_id
            )
            raise

    def get_last_positions(
        self, device_ids: Optional[List[int]] = None
    ) -> List[Dict]:
        """
        GET /api/positions

        Retorna la última posición conocida de todos los dispositivos,
        o solo de los especificados en ``device_ids``.

        :param device_ids: Lista de IDs de dispositivos Traccar. None = todos.
        :returns: Lista de dicts de posición.
        :raises TraccarAPIError: Ante cualquier error de comunicación o HTTP.
        """
        params: Dict = {}
        if device_ids:
            # Traccar acepta múltiples parámetros deviceId repetidos;
            # requests los serializa correctamente si se pasa una lista.
            params["deviceId"] = device_ids

        try:
            result = self._get("positions", params=params or None)
            if not isinstance(result, list):
                _logger.warning(
                    "TraccarService.get_last_positions: respuesta inesperada: %s", type(result)
                )
                return []
            _logger.info(
                "TraccarService.get_last_positions: %d posiciones obtenidas.", len(result)
            )
            return result
        except TraccarAPIError:
            _logger.exception("TraccarService.get_last_positions: fallo.")
            raise

    def get_position_history(
        self,
        device_id: int,
        from_dt: datetime,
        to_dt: datetime,
        max_records: int = 10000,
    ) -> List[Dict]:
        """
        GET /api/positions?deviceId=X&from=ISO&to=ISO

        Descarga el historial de posiciones de un dispositivo en un rango
        temporal. Traccar puede paginar; esta implementación solicita todo
        de una vez (el servidor trunca si supera su límite interno).

        :param device_id: ID del dispositivo en Traccar.
        :param from_dt: Inicio del rango (datetime naive UTC o aware).
        :param to_dt: Fin del rango (datetime naive UTC o aware).
        :param max_records: Límite de registros a solicitar (no siempre respetado por el servidor).
        :returns: Lista de dicts de posición en orden cronológico ascendente.
        :raises TraccarAPIError: Ante cualquier error de comunicación o HTTP.
        :raises ValueError: Si los parámetros son inválidos.
        """
        if not isinstance(device_id, int) or device_id <= 0:
            raise ValueError(f"device_id inválido: {device_id!r}")
        if from_dt >= to_dt:
            raise ValueError("from_dt debe ser anterior a to_dt.")

        params = {
            "deviceId": device_id,
            "from": self._to_iso8601(from_dt),
            "to": self._to_iso8601(to_dt),
        }

        _logger.info(
            "TraccarService.get_position_history: device_id=%d from=%s to=%s",
            device_id,
            params["from"],
            params["to"],
        )

        try:
            result = self._get("positions", params=params)
            if not isinstance(result, list):
                _logger.warning(
                    "TraccarService.get_position_history: respuesta inesperada: %s",
                    type(result),
                )
                return []

            # Ordenar por fixTime ascendente para facilitar el procesamiento posterior
            def _sort_key(p):
                ts = p.get("fixTime") or p.get("deviceTime") or ""
                return ts

            result.sort(key=_sort_key)

            if len(result) > max_records:
                _logger.warning(
                    "TraccarService.get_position_history: resultado truncado a %d/%d registros.",
                    max_records,
                    len(result),
                )
                result = result[:max_records]

            _logger.info(
                "TraccarService.get_position_history: %d posiciones para device_id=%d.",
                len(result),
                device_id,
            )
            return result

        except TraccarAPIError:
            _logger.exception(
                "TraccarService.get_position_history: fallo para device_id=%d.", device_id
            )
            raise

    def get_device_status(self, device_id: int) -> str:
        """
        Determina el estado de un dispositivo consultando /api/devices.

        :param device_id: ID del dispositivo en Traccar.
        :returns: ``'online'``, ``'offline'`` o ``'unknown'``.
        """
        if not isinstance(device_id, int) or device_id <= 0:
            _logger.warning(
                "TraccarService.get_device_status: device_id inválido: %r", device_id
            )
            return "unknown"

        try:
            # Filtrar por ID específico
            result = self._get("devices", params={"id": device_id})
            devices = result if isinstance(result, list) else [result] if result else []

            if not devices:
                _logger.info(
                    "TraccarService.get_device_status: device_id=%d no encontrado.", device_id
                )
                return "unknown"

            device = devices[0]
            status = device.get("status", "unknown").lower()

            # Traccar devuelve: "online", "offline", "unknown"
            if status in ("online", "offline", "unknown"):
                return status

            # Compatibilidad con versiones antiguas que usan booleano
            if device.get("online") is True:
                return "online"
            if device.get("online") is False:
                return "offline"

            return "unknown"

        except TraccarNotFoundError:
            return "unknown"
        except TraccarAPIError as exc:
            _logger.error(
                "TraccarService.get_device_status: error para device_id=%d — %s",
                device_id,
                exc,
            )
            return "unknown"

    def create_device(
        self,
        name: str,
        unique_id: str,
        group_id: Optional[int] = None,
    ) -> Dict:
        """
        POST /api/devices

        Registra un nuevo dispositivo en Traccar.

        :param name: Nombre descriptivo del dispositivo.
        :param unique_id: Identificador único (p.ej. IMEI o número de teléfono).
        :param group_id: ID del grupo Traccar (opcional).
        :returns: Dict del dispositivo creado (incluye su ``id`` asignado por Traccar).
        :raises ValueError: Si los parámetros obligatorios están vacíos.
        :raises TraccarAPIError: Ante cualquier error de comunicación o HTTP.
        """
        if not name or not name.strip():
            raise ValueError("El nombre del dispositivo no puede estar vacío.")
        if not unique_id or not unique_id.strip():
            raise ValueError("El unique_id del dispositivo no puede estar vacío.")

        payload: Dict = {
            "name": name.strip(),
            "uniqueId": unique_id.strip(),
        }
        if group_id is not None:
            payload["groupId"] = group_id

        try:
            result = self._post("devices", payload)
            if not isinstance(result, dict):
                raise TraccarAPIError(
                    f"Respuesta inesperada al crear dispositivo: {result!r}"
                )
            _logger.info(
                "TraccarService.create_device: dispositivo '%s' creado con id=%s.",
                name,
                result.get("id"),
            )
            return result
        except TraccarAPIError:
            _logger.exception(
                "TraccarService.create_device: fallo al crear dispositivo '%s'.", name
            )
            raise

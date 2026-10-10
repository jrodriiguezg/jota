"""
Gestor de conexiones con dispositivos Android para Jota Bridge.
Mantiene los sockets activos y coordina el envio de eventos (timbre, portapapeles, enlaces)
y el almacenamiento del estado reportado (bateria, conectividad).
"""

import asyncio
import logging
import time
from typing import Any

from starlette.websockets import WebSocket, WebSocketState

logger = logging.getLogger(__name__)


class PhoneConnectionManager:
    """Gestiona conexiones WebSocket activas con telefonos Android vinculados."""

    def __init__(self) -> None:
        # device_id -> WebSocket
        self._connections: dict[str, WebSocket] = {}
        # device_id -> metadatos y estado del telefono
        self._device_info: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def register(
        self, device_id: str, websocket: WebSocket, metadata: dict[str, Any] | None = None
    ) -> None:
        """Registra una nueva conexion de dispositivo Android cerrando sockets previos huérfanos."""
        async with self._lock:
            old_ws = self._connections.get(device_id)
            if old_ws and old_ws != websocket:
                try:
                    await old_ws.close(code=1000)
                except Exception:
                    pass
            self._connections[device_id] = websocket
            self._device_info[device_id] = {
                "device_id": device_id,
                "model": (metadata or {}).get("model", "Android Device"),
                "battery": (metadata or {}).get("battery", None),
                "is_charging": (metadata or {}).get("is_charging", False),
                "connected_at": time.time(),
                "last_seen": time.time(),
            }
        logger.info("Dispositivo Android conectado al Bridge: '%s'", device_id)

    async def unregister(self, device_id: str) -> None:
        """Elimina una conexion desconectada."""
        async with self._lock:
            self._connections.pop(device_id, None)
            if device_id in self._device_info:
                self._device_info[device_id]["connected_at"] = None
        logger.info("Dispositivo Android desconectado del Bridge: '%s'", device_id)

    def is_connected(self, device_id: str | None = None) -> bool:
        """Verifica si hay al menos un dispositivo Android conectado (o uno especifico)."""
        if device_id:
            ws = self._connections.get(device_id)
            return ws is not None and ws.client_state == WebSocketState.CONNECTED
        return any(ws.client_state == WebSocketState.CONNECTED for ws in self._connections.values())

    def list_connected_devices(self) -> list[dict[str, Any]]:
        """Lista los dispositivos conectados actualmente."""
        return [
            info
            for did, info in self._device_info.items()
            if self.is_connected(did)
        ]

    def update_device_status(self, device_id: str, status_data: dict[str, Any]) -> None:
        """Actualiza el estado reportado por el dispositivo (bateria, etc.)."""
        if device_id not in self._device_info:
            self._device_info[device_id] = {"device_id": device_id}
        self._device_info[device_id].update(status_data)
        self._device_info[device_id]["last_seen"] = time.time()
        logger.debug("Estado de '%s' actualizado: %s", device_id, status_data)

    def get_device_status(self, device_id: str | None = None) -> dict[str, Any]:
        """
        Retorna el estado de un dispositivo especifico o del primer dispositivo conectado.
        """
        if device_id and device_id in self._device_info:
            return self._device_info[device_id]
        if self._device_info:
            first_key = next(iter(self._device_info))
            return self._device_info[first_key]
        return {
            "device_id": None,
            "connected": False,
            "battery": None,
            "is_charging": False,
            "message": "Ningun dispositivo movil vinculado.",
        }

    async def send_event(
        self, event_type: str, payload: dict[str, Any], device_id: str | None = None
    ) -> bool:
        """
        Envia un evento JSON a traves del WebSocket al dispositivo.
        Si device_id es None, se difunde al primer dispositivo activo.
        """
        target_ws: list[WebSocket] = []
        if device_id and device_id in self._connections:
            target_ws.append(self._connections[device_id])
        else:
            target_ws.extend(
                ws
                for ws in self._connections.values()
                if ws.client_state == WebSocketState.CONNECTED
            )

        if not target_ws:
            logger.warning(
                "No hay dispositivos moviles conectados para recibir el evento '%s'.",
                event_type,
            )
            return False

        message = {"event": event_type, "payload": payload}
        success = False
        for ws in target_ws:
            try:
                await ws.send_json(message)
                success = True
            except Exception as e:
                logger.error("Error enviando evento '%s' a dispositivo: %s", event_type, e)

        return success

    async def ring_phone(self, device_id: str | None = None, duration_seconds: int = 15) -> bool:
        """Dispara la alarma acustica y vibracion en el telefono."""
        return await self.send_event(
            "ring", {"duration_seconds": duration_seconds, "volume": 1.0}, device_id=device_id
        )

    async def send_clipboard(self, text: str, device_id: str | None = None) -> bool:
        """Envia texto al portapapeles del telefono."""
        return await self.send_event("clipboard", {"text": text}, device_id=device_id)

    async def send_url(self, url: str, device_id: str | None = None) -> bool:
        """Abre una URL en el navegador del telefono."""
        return await self.send_event("open_url", {"url": url}, device_id=device_id)

    async def set_torch(self, state: bool, device_id: str | None = None) -> bool:
        """Enciende o apaga la linterna del telefono."""
        return await self.send_event("torch", {"enabled": state}, device_id=device_id)

    async def set_silent(self, silent: bool, device_id: str | None = None) -> bool:
        """Activa o desactiva el modo silencio en el telefono."""
        return await self.send_event("silent", {"silent": silent}, device_id=device_id)

    async def push_file_to_phone(
        self, filename: str, remote_path: str, size_bytes: int = 0, device_id: str | None = None
    ) -> bool:
        """Notifica al telefono para que descargue automaticamente un archivo del PC."""
        return await self.send_event(
            "receive_file",
            {
                "filename": filename,
                "remote_path": remote_path,
                "size_bytes": size_bytes,
            },
            device_id=device_id,
        )

    async def broadcast_notification(
        self, title: str, message: str, device_id: str | None = None
    ) -> bool:
        """Envia una notificacion de escritorio del PC a dispositivos moviles."""
        return await self.send_event(
            "pc_notification",
            {"title": title, "message": message},
            device_id=device_id,
        )

    async def send_media_status(
        self, media_data: dict[str, Any], device_id: str | None = None
    ) -> bool:
        """Envia el estado multimedia actualizado del PC a dispositivos moviles."""
        return await self.send_event("pc_media", media_data, device_id=device_id)

    async def send_media_handoff(
        self, handoff_data: dict[str, Any], device_id: str | None = None
    ) -> bool:
        """Envia evento de handoff para continuar la reproduccion en el movil."""
        return await self.send_event("media_handoff", handoff_data, device_id=device_id)


# Instancia compartida global del gestor
phone_manager = PhoneConnectionManager()

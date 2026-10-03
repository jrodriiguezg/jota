"""
Herramienta de integracion con el telefono Android (Jota Bridge).
Permite al asistente controlar el dispositivo movil por voz:
hacerlo sonar, consultar su bateria y enviarle texto o enlaces.
"""

import asyncio
import logging
from typing import Any

import httpx

from bridge.config import BRIDGE_API_KEY, BRIDGE_PORT
from bridge.phone_manager import phone_manager

logger = logging.getLogger(__name__)


def phone_control(action: str, value: str = "") -> str:
    """
    Ejecuta una accion sobre el telefono Android vinculado.
    Acciones soportadas:
        - 'ring': Hace sonar el telefono al maximo volumen y vibra.
        - 'status': Consulta la bateria y estado del telefono.
        - 'clipboard': Envia texto al portapapeles del telefono.
        - 'open_url': Abre una URL en el navegador del telefono.
    """
    clean_action = action.lower().strip()
    logger.info("phone_control llamado: accion='%s', valor=%r", clean_action, value)

    # 1. Intentar directamente en memoria si el bridge corre en el mismo proceso
    if phone_manager.is_connected():
        return _execute_in_process(clean_action, value)

    # 2. Si no esta en el mismo proceso, consultar el demonio local del bridge via HTTP
    return _execute_via_http(clean_action, value)


def _execute_in_process(action: str, value: str) -> str:
    """Ejecucion directa usando el PhoneConnectionManager en memoria."""
    loop = None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        pass

    if action in ("ring", "sonar", "alarma"):
        coro = phone_manager.ring_phone()
        if loop and loop.is_running():
            asyncio.create_task(coro)
        else:
            asyncio.run(coro)
        return "Haciendo sonar tu telefono."

    if action in ("status", "estado", "bateria"):
        info = phone_manager.get_device_status()
        batt = info.get("battery")
        if batt is not None:
            charging = "conectado al cargador" if info.get("is_charging") else "no esta cargando"
            return f"Al telefono le queda un {batt}% de bateria y {charging}."
        return "El telefono esta vinculado pero aun no ha reportado nivel de bateria."

    if action in ("clipboard", "portapapeles", "copiar"):
        if not value:
            return "No se especifico ningun texto para enviar al telefono."
        coro = phone_manager.send_clipboard(value)
        if loop and loop.is_running():
            asyncio.create_task(coro)
        else:
            asyncio.run(coro)
        return "Texto copiado al portapapeles de tu movil."

    if action in ("open_url", "url", "enlace", "link"):
        if not value:
            return "No se especifico ninguna URL para enviar al telefono."
        coro = phone_manager.send_url(value)
        if loop and loop.is_running():
            asyncio.create_task(coro)
        else:
            asyncio.run(coro)
        return "Enlace enviado a tu movil."

    return f"Accion telefonica '{action}' no reconocida."


def _execute_via_http(action: str, value: str) -> str:
    """Ejecucion comunicandose con el servidor Bridge local via HTTP."""
    base_url = f"http://127.0.0.1:{BRIDGE_PORT}"
    headers = {"X-Bridge-Key": BRIDGE_API_KEY}

    try:
        with httpx.Client(base_url=base_url, headers=headers, timeout=2.0) as client:
            if action in ("ring", "sonar", "alarma"):
                resp = client.post("/api/v1/phone/ring", json={"duration_seconds": 15})
                if resp.status_code == 200:
                    return "Haciendo sonar tu telefono."
                return "No hay ningun telefono conectado al bridge actualmente."

            if action in ("status", "estado", "bateria"):
                resp = client.get("/api/v1/phone/status")
                if resp.status_code == 200:
                    data: dict[str, Any] = resp.json()
                    batt = data.get("battery")
                    if batt is not None:
                        is_ch = data.get("is_charging")
                        charging = "conectado al cargador" if is_ch else "no esta cargando"
                        return f"Al movil le queda un {batt}% de bateria y {charging}."
                    return (
                        "El telefono esta conectado pero no ha reportado su porcentaje de bateria."
                    )
                return "No hay ningun telefono conectado al bridge."

            if action in ("clipboard", "portapapeles", "copiar"):
                if not value:
                    return "No indicaste ningun texto para el portapapeles."
                resp = client.post("/api/v1/phone/clipboard", json={"text": value})
                if resp.status_code == 200:
                    return "Copiado al portapapeles de tu telefono."
                return "No se pudo enviar al telefono; comprueba la conexion."

            if action in ("open_url", "url", "enlace", "link"):
                if not value:
                    return "No indicaste ninguna URL para enviar."
                resp = client.post("/api/v1/phone/url", json={"url": value})
                if resp.status_code == 200:
                    return "Enlace abierto en tu telefono."
                return "No se pudo enviar el enlace al telefono."

    except Exception as e:
        logger.debug("Servidor Bridge local no disponible en %s: %s", base_url, e)

    return "El servicio Jota Bridge no esta activo o no hay ningun telefono vinculado."

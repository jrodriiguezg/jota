"""
Herramienta de integracion con el telefono Android (Jota Bridge).
Permite al asistente controlar el dispositivo movil por voz:
hacerlo sonar, consultar su bateria y enviarle texto o enlaces.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx

from bridge.config import BRIDGE_API_KEY, BRIDGE_PORT, BRIDGE_TEMP_DIR
from bridge.pc_ops import resolve_safe_file_path
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


def _resolve_file_for_phone(query: str) -> Path | None:
    """Localiza un archivo del PC solicitado para enviar al telefono."""
    clean = query.strip()
    if not clean:
        return None

    # Caso especial: capturas de pantalla
    if any(k in clean.lower() for k in ("captura", "screenshot", "pantalla")):
        candidates: list[Path] = []
        for base in [
            Path.home() / "Imágenes" / "Capturas",
            Path.home() / "Pictures" / "Screenshots",
            Path.home() / "Imágenes",
            Path.home() / "Pictures",
            BRIDGE_TEMP_DIR,
        ]:
            if base.exists():
                candidates.extend(base.glob("*.png"))
                candidates.extend(base.glob("*.jpg"))
        if candidates:
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return candidates[0]

        from jota.tools.screenshot import take_screenshot_to_clipboard
        take_screenshot_to_clipboard()
        for base in [Path.home() / "Imágenes", BRIDGE_TEMP_DIR]:
            if base.exists():
                candidates.extend(base.glob("*.png"))
        if candidates:
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return candidates[0]

    # Intentar resolver como ruta segura directa
    try:
        p = resolve_safe_file_path(clean)
        if p.is_file():
            return p
    except Exception:
        pass

    # Buscar por coincidencia de nombre en Descargas o Documentos
    for folder in [
        Path.home() / "Descargas",
        Path.home() / "Downloads",
        Path.home() / "Documentos",
        Path.home(),
    ]:
        if folder.exists():
            matches = [m for m in folder.glob(f"*{clean}*") if m.is_file()]
            if matches:
                matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                return matches[0]

    return None


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

    if action in ("torch", "linterna", "flash"):
        state = value.lower().strip() not in ("off", "apagar", "false", "0", "desactivar")
        coro = phone_manager.set_torch(state)
        if loop and loop.is_running():
            asyncio.create_task(coro)
        else:
            asyncio.run(coro)
        return "Linterna del movil encendida." if state else "Linterna del movil apagada."

    if action in ("silent", "silencio", "dnd", "nomolestar"):
        silent_state = value.lower().strip() not in ("off", "desactivar", "false", "0", "sonar")
        coro = phone_manager.set_silent(silent_state)
        if loop and loop.is_running():
            asyncio.create_task(coro)
        else:
            asyncio.run(coro)
        return (
            "Modo silencio activado en el telefono."
            if silent_state
            else "Modo silencio desactivado en el telefono."
        )

    if action in ("send_file", "sendfile", "enviar_archivo", "enviararchivo", "archivo"):
        target_file = _resolve_file_for_phone(value)
        if not target_file:
            return f"No encontre el archivo '{value}' para enviar."
        try:
            rel_path = str(target_file.relative_to(Path.home()))
        except ValueError:
            rel_path = str(target_file)
        coro = phone_manager.push_file_to_phone(
            filename=target_file.name,
            remote_path=rel_path,
            size_bytes=target_file.stat().st_size,
        )
        if loop and loop.is_running():
            asyncio.create_task(coro)
        else:
            asyncio.run(coro)
        return f"Enviando '{target_file.name}' a tu telefono."

    if action in ("status", "estado", "bateria"):
        devices = phone_manager.list_connected_devices()
        if len(devices) > 1:
            res = []
            for d in devices:
                did = d.get("device_id", "Dispositivo")
                model = d.get("model", "")
                name = f"{did} ({model})" if model else did
                batt = d.get("battery")
                if batt is not None:
                    chg = "cargando" if d.get("is_charging") else "sin cargar"
                    res.append(f"{name}: {batt}% ({chg})")
                else:
                    res.append(f"{name}: bateria no reportada")
            return "Estado de tus dispositivos conectados: " + "; ".join(res) + "."

        info = phone_manager.get_device_status()
        batt = info.get("battery")
        if batt is not None:
            charging = "conectado al cargador" if info.get("is_charging") else "no esta cargando"
            device_name = info.get("device_id")
            prefix = f"A {device_name}" if device_name else "Al telefono"
            return f"{prefix} le queda un {batt}% de bateria y {charging}."
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
                dev_resp = client.get("/api/v1/phone/devices")
                if dev_resp.status_code == 200:
                    devices = dev_resp.json().get("devices", [])
                    if len(devices) > 1:
                        res = []
                        for d in devices:
                            did = d.get("device_id", "Dispositivo")
                            model = d.get("model", "")
                            name = f"{did} ({model})" if model else did
                            batt = d.get("battery")
                            if batt is not None:
                                chg = "cargando" if d.get("is_charging") else "sin cargar"
                                res.append(f"{name}: {batt}% ({chg})")
                            else:
                                res.append(f"{name}: sin datos de bateria")
                        return "Estado de tus dispositivos: " + "; ".join(res) + "."

                resp = client.get("/api/v1/phone/status")
                if resp.status_code == 200:
                    data: dict[str, Any] = resp.json()
                    batt = data.get("battery")
                    if batt is not None:
                        is_ch = data.get("is_charging")
                        charging = "conectado al cargador" if is_ch else "no esta cargando"
                        did = data.get("device_id")
                        prefix = f"A {did}" if did else "Al movil"
                        return f"{prefix} le queda un {batt}% de bateria y {charging}."
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

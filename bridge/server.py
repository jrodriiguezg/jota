"""
Servidor FastAPI para Jota Bridge.
Expone endpoints REST y canal WebSocket para comunicacion remota via Tailscale
con dispositivos Android.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from bridge.config import (
    AUTH_RATE_LIMIT_MAX_FAILURES,
    AUTH_RATE_LIMIT_WINDOW_SECONDS,
    BRIDGE_API_KEY,
    BRIDGE_HOST,
    BRIDGE_PORT,
    BRIDGE_TEMP_DIR,
    ENABLE_AUTO_ADB_REVERSE,
    ENABLE_MDNS_DISCOVERY,
    MAX_FILE_UPLOAD_BYTES,
)
from bridge.pc_ops import (
    capture_screen_bytes,
    execute_pc_action,
    get_clipboard_text,
    get_pc_network_info,
    get_pc_screenshots,
    get_system_status,
    resolve_safe_file_path,
    resolve_screenshot_file,
    set_clipboard_text,
)
from bridge.phone_manager import phone_manager
from bridge.voice_pipeline import process_remote_text, process_remote_voice

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("jota.bridge")

# Registro en memoria de intentos fallidos de autenticacion: ip -> lista de timestamps
_failed_auth_log: dict[str, list[float]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida del servidor Bridge."""
    BRIDGE_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("==================================================")
    logger.info("  Jota Bridge activo en http://%s:%s", BRIDGE_HOST, BRIDGE_PORT)
    logger.info("  Canal de vinculacion Android listo en /ws/phone")
    logger.info("==================================================")

    # 1. Registro mDNS / ZeroConf para auto-descubrimiento en LAN
    mdns_handle = None
    if ENABLE_MDNS_DISCOVERY:
        try:
            from bridge.discovery import register_mdns_service

            mdns_handle = await register_mdns_service(port=BRIDGE_PORT)
        except Exception as e:
            logger.debug("mDNS discovery no disponible: %s", e)

    # 2. Configuracion de ADB Reverse si el movil esta conectado por cable USB
    if ENABLE_AUTO_ADB_REVERSE:
        try:
            from bridge.discovery import setup_adb_reverse

            ok_adb, msg_adb = setup_adb_reverse(port=BRIDGE_PORT)
            if ok_adb:
                logger.info("USB ADB: %s", msg_adb)
        except Exception as e:
            logger.debug("ADB reverse no disponible: %s", e)

    try:
        from jota.llm import load_model

        load_model()
    except Exception as e:
        logger.warning("No se pudo pre-cargar el modelo LLM en el Bridge: %s", e)

    # 3. Monitor en segundo plano para sincronizacion universal del portapapeles
    clip_task = None
    async def monitor_clipboard():
        try:
            last_clip = get_clipboard_text()
        except Exception:
            last_clip = ""
        while True:
            await asyncio.sleep(1.2)
            try:
                current = get_clipboard_text()
                if current and current != last_clip and len(current) < 20000:
                    last_clip = current
                    await phone_manager.send_clipboard(current)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    clip_task = asyncio.create_task(monitor_clipboard())

    # 4. Listener de la tecla Copilot para push-to-talk en el PC
    copilot_service = None
    try:
        from jota.service import CopilotVoiceService

        copilot_service = CopilotVoiceService()
        copilot_service.start()
        logger.info("Copilot Push-to-Talk activo en PC: pulsa Copilot para hablar.")
    except Exception as e:
        logger.info("Listener de tecla Copilot local no iniciado en Bridge: %s", e)

    yield

    # Limpieza al apagar
    if copilot_service:
        try:
            copilot_service.stop()
        except Exception:
            pass

    if clip_task:
        clip_task.cancel()

    if mdns_handle:
        try:
            from bridge.discovery import unregister_mdns_service

            await unregister_mdns_service(mdns_handle)
        except Exception:
            pass

    logger.info("Deteniendo Jota Bridge...")


app = FastAPI(
    title="Jota Bridge API",
    description="Puente de comunicacion bidireccional entre Jota y dispositivos Android.",
    version="0.1.0",
    lifespan=lifespan,
)

# Permitir CORS para clientes web/PWA o herramientas de depuracion
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_auth(
    request: Request = None,
    x_bridge_key: str | None = Header(None, alias="X-Bridge-Key"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> None:
    """Valida la clave secreta enviada en cabecera HTTP con proteccion contra fuerza bruta."""
    client_ip = (request.client.host if request and request.client else "unknown")
    now = time.time()

    # Comprobar intentos fallidos previos para esta IP
    attempts = _failed_auth_log.get(client_ip, [])
    valid_attempts = [t for t in attempts if (now - t) < AUTH_RATE_LIMIT_WINDOW_SECONDS]
    _failed_auth_log[client_ip] = valid_attempts

    if len(valid_attempts) >= AUTH_RATE_LIMIT_MAX_FAILURES:
        logger.warning("Bloqueo por rate limiting de autenticacion para IP %s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos fallidos de autenticacion. Espera 60 segundos.",
        )

    token = None
    if x_bridge_key:
        token = x_bridge_key
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    if token != BRIDGE_API_KEY:
        _failed_auth_log.setdefault(client_ip, []).append(now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticacion denegada: clave invalida o ausente.",
        )

    # Limpiar registro al autenticar con exito
    if client_ip in _failed_auth_log:
        _failed_auth_log.pop(client_ip, None)


# ── Modelos de Peticion ──────────────────────────────────────────────────────


class PcActionPayload(BaseModel):
    action: str


class ClipboardPayload(BaseModel):
    text: str


class TextPromptPayload(BaseModel):
    prompt: str
    generate_audio: bool = False
    play_on_pc: bool = False


class RingPhonePayload(BaseModel):
    duration_seconds: int = 15
    device_id: str | None = None


class PhoneClipboardPayload(BaseModel):
    text: str
    device_id: str | None = None


class PhoneUrlPayload(BaseModel):
    url: str
    device_id: str | None = None


# ── Endpoints de Salud y Estado ──────────────────────────────────────────────


@app.get("/health")
@app.get("/api/v1/health")
def health_check():
    """Comprobacion de estado del servicio Bridge."""
    return {
        "status": "online",
        "service": "jota-bridge",
        "connected_phones": len(phone_manager.list_connected_devices()),
    }


# ── Endpoints de Control y Operaciones del PC ────────────────────────────────


@app.get("/api/v1/pc/status", dependencies=[Depends(verify_auth)])
def pc_status():
    """Retorna estado del PC (CPU, RAM, Disco, Ventana activa en Hyprland)."""
    return get_system_status()


@app.get("/api/v1/pc/channels", dependencies=[Depends(verify_auth)])
def pc_channels():
    """
    Retorna estado de los canales de conexion cercanos (WiFi/LAN, Cable USB ADB, Bluetooth PAN).
    """
    from bridge.discovery import get_nearby_channels_status

    return get_nearby_channels_status(port=BRIDGE_PORT)


@app.post("/api/v1/pc/channels/adb-reverse", dependencies=[Depends(verify_auth)])
def pc_trigger_adb_reverse():
    """Fuerza la configuracion de ADB reverse sobre USB para el dispositivo conectado."""
    from bridge.discovery import setup_adb_reverse

    ok, msg = setup_adb_reverse(port=BRIDGE_PORT)
    return {"success": ok, "message": msg}



@app.get("/api/v1/pc/screenshot", dependencies=[Depends(verify_auth)])
def pc_screenshot(
    format: str = Query("png", description="Formato de imagen: 'png' o 'jpeg'/'jpg'"),
    quality: int = Query(80, ge=10, le=100, description="Calidad de compresion JPEG (10-100)"),
    scale: float = Query(1.0, ge=0.1, le=1.0, description="Escala de resolucion (0.1 a 1.0)"),
):
    """Captura la pantalla actual de Wayland y la devuelve optimizada para red movil."""
    try:
        clean_fmt = format.lower().strip()
        media_type = "image/jpeg" if clean_fmt in ("jpeg", "jpg") else "image/png"
        image_bytes = capture_screen_bytes(
            save_history=True, format=clean_fmt, quality=quality, scale=scale
        )
        return Response(content=image_bytes, media_type=media_type)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/v1/pc/screenshots", dependencies=[Depends(verify_auth)])
def pc_screenshots(limit: int = 50):
    """Retorna historial cronologico de capturas de pantalla disponibles en el PC."""
    return {"screenshots": get_pc_screenshots(limit=limit)}


@app.get("/api/v1/pc/screenshots/file", dependencies=[Depends(verify_auth)])
def pc_screenshot_file(name: str = Query(..., description="Nombre o ruta relativa de la captura")):
    """Devuelve el archivo binario de una captura de pantalla especifica del PC."""
    file_path = resolve_screenshot_file(name)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Captura de pantalla no encontrada.")
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="image/png",
    )


@app.post("/api/v1/pc/screenshots/capture", dependencies=[Depends(verify_auth)])
def pc_capture_screenshot():
    """Toma una nueva captura de pantalla en el PC y la registra en el historial."""
    try:
        capture_screen_bytes(save_history=True)
        return {
            "success": True,
            "message": "Captura realizada correctamente.",
            "screenshots": get_pc_screenshots(limit=50),
        }
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/pc/clipboard", dependencies=[Depends(verify_auth)])
def pc_get_clipboard():
    """Obtiene el contenido actual del portapapeles del PC."""
    return {"text": get_clipboard_text()}


@app.post("/api/v1/pc/clipboard", dependencies=[Depends(verify_auth)])
def pc_set_clipboard(payload: ClipboardPayload):
    """Establece el texto en el portapapeles del PC."""
    ok = set_clipboard_text(payload.text)
    if not ok:
        raise HTTPException(status_code=500, detail="Error al escribir en el portapapeles del PC.")
    return {"success": True}


@app.post("/api/v1/pc/action", dependencies=[Depends(verify_auth)])
def pc_action(payload: PcActionPayload):
    """Ejecuta una accion rapida en el PC (lock, mute, play_pause, vol_up, etc.)."""
    ok, message = execute_pc_action(payload.action)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@app.get("/api/v1/pc/network", dependencies=[Depends(verify_auth)])
def pc_network():
    """Obtiene datos de red del PC (interfaces y direcciones MAC para Wake-on-LAN)."""
    return get_pc_network_info()


@app.get("/api/v1/bridge/pairing")
def bridge_pairing():
    """Obtiene los parametros de emparejamiento con el PC para la app Android."""
    from bridge.qr import get_pairing_payload
    return get_pairing_payload()


@app.get("/api/v1/pc/file", dependencies=[Depends(verify_auth)])
def pc_download_file(path: str = Query(..., description="Ruta absoluta o relativa al home")):
    """
    Descarga un archivo del PC al dispositivo movil con validacion de seguridad.
    """
    try:
        safe_path = resolve_safe_file_path(path)
        return FileResponse(
            path=str(safe_path),
            filename=safe_path.name,
            media_type="application/octet-stream",
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.post("/api/v1/pc/upload", dependencies=[Depends(verify_auth)])
async def pc_upload_file(file: UploadFile = File(...)):
    """
    Recibe un archivo o imagen compartido desde el movil y lo guarda en ~/Descargas o ~/Downloads.
    """
    try:
        downloads_dir = Path.home() / "Descargas"
        if not downloads_dir.exists():
            downloads_dir = Path.home() / "Downloads"
            downloads_dir.mkdir(parents=True, exist_ok=True)

        filename = Path(file.filename or "archivo_movil").name
        # Guardrail contra extensiones ejecutables directas
        dangerous_exts = {".sh", ".bash", ".exe", ".bin", ".desktop", ".so"}
        if Path(filename).suffix.lower() in dangerous_exts:
            filename = f"{filename}.safe"

        content = await file.read()
        if len(content) > MAX_FILE_UPLOAD_BYTES:
            max_mb = MAX_FILE_UPLOAD_BYTES // (1024 * 1024)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"El archivo supera el limite maximo de subida de {max_mb} MB.",
            )

        dest_path = downloads_dir / filename
        counter = 1
        stem = dest_path.stem
        suffix = dest_path.suffix
        while dest_path.exists():
            dest_path = downloads_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        dest_path.write_bytes(content)

        from jota.tools.system import send_desktop_notification

        send_desktop_notification("JotaLink", f"Archivo recibido del movil: {dest_path.name}")

        return {
            "success": True,
            "filename": dest_path.name,
            "path": str(dest_path),
            "size_bytes": len(content),
        }
    except Exception as e:
        logger.error("Error al recibir archivo del movil: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Endpoints de Invocacion de Jota (Voz y Texto) ─────────────────────────────


@app.post("/api/v1/voice/ask", dependencies=[Depends(verify_auth)])
async def ask_voice(
    file: UploadFile = File(...),
    generate_audio: bool = Form(True),
    play_on_pc: bool = Form(True),
):
    """
    Recibe un audio grabado desde el movil, ejecuta Whisper STT, consulta al LLM Qwen3,
    ejecuta herramientas del PC si aplica y sintetiza respuesta TTS en WAV.
    Reproduce simultaneamente en el PC y devuelve el audio al movil.
    """
    audio_bytes = await file.read()
    result = process_remote_voice(
        audio_bytes,
        generate_audio=generate_audio,
        play_on_pc=play_on_pc,
    )
    return result


@app.post("/api/v1/text/ask", dependencies=[Depends(verify_auth)])
def ask_text(payload: TextPromptPayload):
    """
    Consulta escrita directa a Jota desde el movil.
    """
    result = process_remote_text(
        payload.prompt,
        generate_audio=payload.generate_audio,
        play_on_pc=payload.play_on_pc,
    )
    return result


@app.get("/api/v1/audio/{audio_id}", dependencies=[Depends(verify_auth)])
def download_audio_response(audio_id: str):
    """Permite al movil descargar el archivo WAV sintetizado por el TTS."""
    safe_name = Path(audio_id).name
    audio_path = BRIDGE_TEMP_DIR / safe_name
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio no encontrado o expirado.")
    return FileResponse(path=str(audio_path), media_type="audio/wav")


# ── Endpoints de Control sobre el Telefono Movil ─────────────────────────────


@app.post("/api/v1/phone/ring", dependencies=[Depends(verify_auth)])
async def trigger_ring_phone(payload: RingPhonePayload):
    """Hace sonar la alarma y vibrar el telefono vinculado."""
    ok = await phone_manager.ring_phone(
        device_id=payload.device_id, duration_seconds=payload.duration_seconds
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay ningun telefono conectado para sonar.",
        )
    return {"success": True, "message": "Comando de alarma enviado al telefono."}


@app.post("/api/v1/phone/clipboard", dependencies=[Depends(verify_auth)])
async def send_clipboard_to_phone(payload: PhoneClipboardPayload):
    """Envia texto al portapapeles del telefono."""
    ok = await phone_manager.send_clipboard(text=payload.text, device_id=payload.device_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay ningun telefono conectado para recibir el portapapeles.",
        )
    return {"success": True, "message": "Texto enviado al telefono."}


@app.post("/api/v1/phone/url", dependencies=[Depends(verify_auth)])
async def send_url_to_phone(payload: PhoneUrlPayload):
    """Abre una URL en el navegador del telefono."""
    ok = await phone_manager.send_url(url=payload.url, device_id=payload.device_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay ningun telefono conectado para abrir el enlace.",
        )
    return {"success": True, "message": "Enlace enviado al telefono."}


@app.get("/api/v1/phone/status", dependencies=[Depends(verify_auth)])
def get_phone_status(device_id: str | None = None):
    """Obtiene el ultimo estado reportado por el telefono (bateria, etc.)."""
    return phone_manager.get_device_status(device_id=device_id)


@app.get("/api/v1/phone/devices", dependencies=[Depends(verify_auth)])
def get_phone_devices():
    """Lista todos los dispositivos Android conectados actualmente."""
    return {"devices": phone_manager.list_connected_devices()}


# ── Canal WebSocket para la Aplicacion Android ───────────────────────────────


@app.websocket("/ws/phone")
async def phone_websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(None),
    device_id: str = Query("android_primary"),
    model: str = Query("Android Device"),
):
    """
    Canal de comunicacion persistente para la aplicacion Android.
    Mantiene la conexion abierta, recibe reportes de bateria y escucha comandos
    de alarma, portapapeles y enlaces enviados desde el PC.
    """
    # Validar autenticacion
    if token != BRIDGE_API_KEY:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    await phone_manager.register(
        device_id=device_id,
        websocket=websocket,
        metadata={"model": model},
    )

    try:
        # Enviar confirmacion de conexion inicial
        await websocket.send_json(
            {
                "event": "connected",
                "message": "Vinculado correctamente con Jota Bridge",
                "pc_status": get_system_status(),
            }
        )

        while True:
            data: dict[str, Any] = await websocket.receive_json()
            event = data.get("event")
            payload = data.get("payload", {})

            if event == "status_update":
                phone_manager.update_device_status(device_id, payload)
            elif event == "ping":
                phone_manager.update_device_status(device_id, {})
                await websocket.send_json({"event": "pong"})
            elif event == "pc_action":
                action = payload.get("action", "")
                ok, msg = execute_pc_action(action)
                await websocket.send_json(
                    {
                        "event": "pc_action_result",
                        "payload": {"action": action, "success": ok, "message": msg},
                    }
                )
            elif event == "get_status":
                await websocket.send_json(
                    {"event": "pc_status", "payload": get_system_status()}
                )
            elif event == "clipboard":
                text = payload.get("text", "")
                ok = set_clipboard_text(text)
                await websocket.send_json(
                    {"event": "clipboard_result", "payload": {"success": ok}}
                )
            elif event == "ask_text":
                prompt = payload.get("prompt", "")
                gen_audio = payload.get("generate_audio", False)
                play_pc = payload.get("play_on_pc", False)
                res = process_remote_text(prompt, generate_audio=gen_audio, play_on_pc=play_pc)
                await websocket.send_json(
                    {"event": "ask_text_result", "payload": res}
                )
            else:
                logger.debug("Mensaje no reconocido desde el telefono: %s", data)

    except WebSocketDisconnect:
        await phone_manager.unregister(device_id)
    except Exception as e:
        logger.error("Error en WebSocket de telefono '%s': %s", device_id, e)
        await phone_manager.unregister(device_id)


def main():
    """Punto de entrada de consola para arrancar el servidor Jota Bridge."""
    uvicorn.run(app, host=BRIDGE_HOST, port=BRIDGE_PORT, log_level="info")


if __name__ == "__main__":
    main()

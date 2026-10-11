"""
Servidor FastAPI para Jota Bridge.
Expone endpoints REST y canal WebSocket para comunicacion remota via Tailscale
con dispositivos Android.
"""

import asyncio
import hmac
import json
import logging
import re
import shutil
import subprocess
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
            if not phone_manager.is_connected():
                continue
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

    # 3b. Monitor en segundo plano para sincronizacion de estado multimedia
    media_task = None
    async def monitor_media():
        from bridge.pc_ops import get_media_status

        last_sig = None
        while True:
            await asyncio.sleep(1.5)
            if not phone_manager.is_connected():
                continue
            try:
                cur_media = get_media_status()
                sig = (
                    cur_media.get("status"),
                    cur_media.get("title"),
                    cur_media.get("artist"),
                    cur_media.get("player"),
                )
                if sig != last_sig:
                    last_sig = sig
                    await phone_manager.send_media_status(cur_media)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    media_task = asyncio.create_task(monitor_media())

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

    if media_task:
        media_task.cancel()

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
    if valid_attempts:
        _failed_auth_log[client_ip] = valid_attempts
    else:
        _failed_auth_log.pop(client_ip, None)

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

    if not token or not hmac.compare_digest(str(token), str(BRIDGE_API_KEY)):
        _failed_auth_log.setdefault(client_ip, []).append(now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticacion denegada: clave invalida o ausente.",
        )

    # Limpiar registro al autenticar con exito
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


class PhoneFilePayload(BaseModel):
    filename: str
    remote_path: str
    size_bytes: int = 0
    device_id: str | None = None


class MediaHandoffPayload(BaseModel):
    title: str = ""
    artist: str = ""
    song_id: str = ""
    position_ms: int = 0
    stream_url: str = ""
    device_id: str | None = None


class HomelabContainerActionPayload(BaseModel):
    name: str
    action: str = "restart"



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


@app.api_route("/download/jotalink.apk", methods=["GET", "HEAD"])
@app.api_route("/api/v1/download/apk", methods=["GET", "HEAD"])
def download_apk():
    """Descarga directa del paquete APK de JotaLink para Android."""
    candidate_paths = [
        Path("data/jotalink.apk"),
        Path("/app/data/jotalink.apk"),
        Path(__file__).parent / "android/app/build/outputs/apk/debug/app-debug.apk",
        Path(__file__).parent.parent / "bridge/android/app/build/outputs/apk/debug/app-debug.apk",
        Path("bridge/android/app/build/outputs/apk/debug/app-debug.apk"),
    ]
    for p in candidate_paths:
        if p.is_file():
            return FileResponse(
                path=str(p),
                media_type="application/vnd.android.package-archive",
                filename="JotaLink.apk",
            )
    raise HTTPException(
        status_code=404,
        detail=(
            "APK no encontrado en el servidor. Compile con ./gradlew assembleDebug "
            "o deposite el binario en data/jotalink.apk."
        ),
    )


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


def _docker_socket_request(
    method: str, path: str, body: bytes | None = None
) -> tuple[int, bytes]:
    """Realiza una solicitud directa al socket UNIX de Docker Engine (/var/run/docker.sock)."""
    import http.client
    import socket

    sock_path = "/var/run/docker.sock"
    if not Path(sock_path).exists():
        return -1, b""

    class UnixHTTPConnection(http.client.HTTPConnection):
        def connect(self):
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(10.0)
            self.sock.connect(sock_path)

    conn = UnixHTTPConnection("localhost")
    try:
        conn.request(method, path, body=body)
        resp = conn.getresponse()
        return resp.status, resp.read()
    except Exception as e:
        logger.debug("Error en conexion al socket de Docker: %s", e)
        return -1, str(e).encode("utf-8")
    finally:
        try:
            conn.close()
        except Exception:
            pass


@app.get("/api/v1/homelab/containers", dependencies=[Depends(verify_auth)])
def homelab_list_containers():
    """Lista todos los contenedores Docker o Podman y su estado en el host."""
    # 1. Probar acceso directo mediante socket UNIX de Docker Engine
    if Path("/var/run/docker.sock").exists():
        try:
            status_code, raw_bytes = _docker_socket_request("GET", "/containers/json?all=true")
            if status_code == 200:
                raw_list = json.loads(raw_bytes.decode("utf-8"))
                containers = []
                for item in raw_list:
                    names = [n.lstrip("/") for n in item.get("Names", [])]
                    name = names[0] if names else item.get("Id", "")[:12]
                    containers.append({
                        "name": name,
                        "image": item.get("Image", ""),
                        "status": item.get("Status", ""),
                        "state": item.get("State", ""),
                    })
                return {"containers": containers, "count": len(containers)}
        except Exception as e:
            logger.debug("Fallo lectura de Docker via socket UNIX: %s", e)

    # 2. Fallback a binario CLI (docker / podman)
    engine = shutil.which("docker") or shutil.which("podman")
    if not engine:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Docker o Podman no esta disponible en este host.",
        )

    try:
        res = subprocess.run(
            [engine, "ps", "-a", "--format", "{{json .}}"],
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
        if res.returncode != 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al listar contenedores: {res.stderr.strip()}",
            )

        containers = []
        for line in res.stdout.strip().splitlines():
            line = line.strip()
            if line:
                try:
                    c = json.loads(line)
                    containers.append({
                        "name": c.get("Names", ""),
                        "image": c.get("Image", ""),
                        "status": c.get("Status", ""),
                        "state": c.get("State", ""),
                    })
                except Exception:
                    pass
        return {"containers": containers, "count": len(containers)}
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Tiempo de espera agotado al consultar contenedores.",
        )
    except Exception as e:
        logger.error("Error en homelab_list_containers: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/api/v1/homelab/container", dependencies=[Depends(verify_auth)])
def homelab_container_action(payload: HomelabContainerActionPayload):
    """Ejecuta una accion (start, stop, restart) sobre un contenedor del homelab."""
    clean_name = payload.name.strip()
    clean_action = payload.action.strip().lower()

    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", clean_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nombre de contenedor invalido. Solo caracteres alfanumericos y guiones.",
        )

    if clean_action not in ("start", "stop", "restart"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Accion no permitida. Solo 'start', 'stop' o 'restart'.",
        )

    # 1. Probar API sobre socket UNIX
    if Path("/var/run/docker.sock").exists():
        try:
            status_code, _ = _docker_socket_request(
                "POST", f"/containers/{clean_name}/{clean_action}"
            )
            if status_code in (204, 200):
                return {
                    "success": True,
                    "message": f"Contenedor '{clean_name}' {clean_action} ejecutado con exito.",
                }
        except Exception as e:
            logger.debug("Fallo accion Docker via socket UNIX: %s", e)

    # 2. Fallback a binario CLI
    engine = shutil.which("docker") or shutil.which("podman")
    if not engine:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Docker o Podman no disponible.",
        )

    try:
        res = subprocess.run(
            [engine, clean_action, clean_name],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if res.returncode == 0:
            return {
                "success": True,
                "message": f"Contenedor '{clean_name}' {clean_action} ejecutado con exito.",
            }
        return {
            "success": False,
            "message": res.stderr.strip() or f"Error ejecutando {clean_action} en '{clean_name}'.",
        }
    except Exception as e:
        logger.error("Error en homelab_container_action: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/api/v1/vision/analyze", dependencies=[Depends(verify_auth)])
async def analyze_mobile_image(
    file: UploadFile = File(...),
    question: str = Form("Que ves en esta imagen?"),
):
    """
    Recibe una imagen o fotografia tomada desde el movil y la analiza con el modelo de vision.
    Devuelve la descripcion textual sintetizada.
    """
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Archivo de imagen vacio.",
        )

    from jota.tools.screen_vision import query_vision_model

    ok, answer = query_vision_model(image_bytes, question=question)
    return {"success": ok, "description": answer}


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


@app.post("/api/v1/phone/send_file", dependencies=[Depends(verify_auth)])
async def send_file_to_phone(payload: PhoneFilePayload):
    """Notifica al telefono para que descargue un archivo del PC."""
    ok = await phone_manager.push_file_to_phone(
        filename=payload.filename,
        remote_path=payload.remote_path,
        size_bytes=payload.size_bytes,
        device_id=payload.device_id,
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay ningun telefono conectado para recibir el archivo.",
        )
    return {"success": True, "message": f"Archivo '{payload.filename}' enviado al telefono."}


@app.post("/api/v1/phone/media_handoff", dependencies=[Depends(verify_auth)])
async def phone_media_handoff(payload: MediaHandoffPayload):
    """Envia orden de transferencia de reproduccion al telefono movil."""
    ok = await phone_manager.send_media_handoff(
        payload.model_dump(), device_id=payload.device_id
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay ningun telefono conectado para recibir la reproduccion.",
        )
    return {"success": True, "message": "Handoff enviado al telefono."}


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
    # Proteccion contra fuerza bruta y escaneo en WebSocket
    client_ip = websocket.client.host if websocket.client else "unknown"
    now = time.time()
    attempts = _failed_auth_log.get(client_ip, [])
    valid_attempts = [t for t in attempts if (now - t) < AUTH_RATE_LIMIT_WINDOW_SECONDS]
    if valid_attempts:
        _failed_auth_log[client_ip] = valid_attempts
    else:
        _failed_auth_log.pop(client_ip, None)

    if len(valid_attempts) >= AUTH_RATE_LIMIT_MAX_FAILURES:
        logger.warning("Bloqueo de WebSocket por rate limiting para IP %s", client_ip)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Validar autenticacion en tiempo constante contra ataques de canal lateral
    if not token or not hmac.compare_digest(str(token), str(BRIDGE_API_KEY)):
        _failed_auth_log.setdefault(client_ip, []).append(now)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    _failed_auth_log.pop(client_ip, None)

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

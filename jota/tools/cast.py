"""
Control y emision de contenidos hacia Smart TVs y dispositivos Chromecast (catt y ADB).
"""

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from jota.tools.context import get_implicit_media_url, resolve_device

logger = logging.getLogger(__name__)

# Rutas conocidas para catt
_VENV_CATT = Path(sys.prefix) / "bin" / "catt"
CATT_BIN = str(_VENV_CATT) if _VENV_CATT.exists() else (shutil.which("catt") or "catt")

# Paquetes comunes para Android TV
TV_APPS: dict[str, str] = {
    "netflix": "com.netflix.ninja",
    "prime": "com.amazon.amazonvideo.livingroom",
    "prime video": "com.amazon.amazonvideo.livingroom",
    "amazon": "com.amazon.amazonvideo.livingroom",
    "youtube": "com.google.android.youtube.tv",
    "plex": "com.plexapp.android",
    "kodi": "org.xbmc.kodi",
    "spotify": "com.spotify.tv.android",
}


def cast_media(target: str = "tele", media_url: str | None = None) -> tuple[bool, str]:
    """
    Emite un contenido multimedia (URL o vídeo) hacia la pantalla o tele indicada.
    Si media_url es None, se toma automaticamente del portapapeles o de lo que este sonando.
    """
    dev = resolve_device(target)
    dev_name = dev.get("name", "Android TV Salón")

    resolved_url = (media_url or "").strip()
    if not resolved_url:
        resolved_url = get_implicit_media_url()

    if not resolved_url:
        return False, f"No encontre ningun enlace o contenido activo para enviar a {dev_name}."

    if not shutil.which(CATT_BIN) and not Path(CATT_BIN).exists():
        return False, "La utilidad 'catt' no esta disponible en el entorno."

    try:
        cmd = [CATT_BIN]
        if dev_name:
            cmd.extend(["-d", dev_name])
        cmd.extend(["cast", resolved_url])

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True, f"Enviando contenido a {dev_name}."
    except Exception as e:
        logger.error("Error al ejecutar catt: %s", e)
        return False, f"Error al emitir en {dev_name}: {e}"


def cast_control(action: str, target: str = "tele") -> tuple[bool, str]:
    """
    Controla la reproduccion de un Cast activo (pause, resume, stop, vol_up, vol_down).
    """
    dev = resolve_device(target)
    dev_name = dev.get("name", "Android TV Salón")

    if not shutil.which(CATT_BIN) and not Path(CATT_BIN).exists():
        return False, "La utilidad 'catt' no esta disponible en el entorno."

    cmd_map = {
        "pause": ("pause", "Reproduccion pausada en la tele."),
        "resume": ("resume", "Reproduccion reanudada en la tele."),
        "play": ("resume", "Reproduccion reanudada en la tele."),
        "stop": ("stop", "Emision detenida en la tele."),
        "rewind": ("rewind", "Rebobinando 30 segundos."),
        "forward": ("forward", "Avanzando 30 segundos."),
        "volume_up": ("volumeup", "Subiendo volumen en la tele."),
        "volume_down": ("volumedown", "Bajando volumen en la tele."),
    }

    if action not in cmd_map:
        return False, f"Accion de cast desconocida: {action}"

    catt_subcmd, ok_msg = cmd_map[action]
    try:
        cmd = [CATT_BIN]
        if dev_name:
            cmd.extend(["-d", dev_name])
        cmd.append(catt_subcmd)

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
        if proc.returncode == 0:
            return True, ok_msg
        return False, f"No se pudo controlar la tele: {proc.stderr.strip()}"
    except Exception as e:
        logger.error("Error en control de cast: %s", e)
        return False, f"Error al enviar orden a {dev_name}: {e}"


def launch_tv_app(app_name: str, target: str = "tele") -> tuple[bool, str]:
    """
    Abre una aplicacion nativa en la Android TV (Netflix, Prime, YouTube) via ADB.
    """
    dev = resolve_device(target)
    adb_target = dev.get("adb", "192.168.1.50:5555")
    clean_app = app_name.lower().strip()

    package = TV_APPS.get(clean_app)
    if not package:
        for k, v in TV_APPS.items():
            if k in clean_app:
                package = v
                break

    if not package:
        return False, f"Aplicacion '{app_name}' no reconocida para la tele."

    if not shutil.which("adb"):
        return False, "ADB no esta instalado en el sistema."

    try:
        cmd = ["adb", "-s", adb_target, "shell", "monkey", "-p", package, "1"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=4, check=False)
        if proc.returncode == 0:
            return True, f"Abriendo {clean_app.title()} en la tele."
        return False, f"Error abriendo {clean_app} en la tele: {proc.stderr.strip()}"
    except Exception as e:
        logger.error("Error lanzando app en TV via ADB: %s", e)
        return False, f"Fallo de conexion con la tele por ADB: {e}"

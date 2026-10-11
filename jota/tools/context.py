"""
Resolucion de contexto implicito para comandos por voz de Jota.
Extrae URLs, ventanas activas y alias de dispositivos sin que el usuario tenga que dictarlos.
"""

import json
import logging
import re
import shutil
import subprocess
from typing import Any

from jota.config import DEVICES

logger = logging.getLogger(__name__)


def get_clipboard_url() -> str:
    """Extrae una URL valida del portapapeles si existe."""
    if not shutil.which("wl-paste"):
        return ""

    try:
        proc = subprocess.run(
            ["wl-paste", "--no-newline"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout:
            raw = proc.stdout.strip()
            match = re.search(r"https?://\S+", raw)
            if match:
                return match.group(0)
    except Exception as e:
        logger.debug("Error leyendo portapapeles para URL: %s", e)

    return ""


def get_active_window_info() -> dict[str, str]:
    """Obtiene la ventana activa y su titulo en Hyprland."""
    if not shutil.which("hyprctl"):
        return {"class": "", "title": ""}

    try:
        proc = subprocess.run(
            ["hyprctl", "activewindow", "-j"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            return {
                "class": data.get("class", ""),
                "title": data.get("title", ""),
            }
    except Exception as e:
        logger.debug("Error leyendo ventana activa: %s", e)

    return {"class": "", "title": ""}


def get_desktop_context() -> dict[str, Any]:
    """Obtiene informacion detallada del entorno y ventana activa en Hyprland."""
    if not shutil.which("hyprctl"):
        return {"class": "", "title": "", "workspace": 1, "fullscreen": False}

    info: dict[str, Any] = {
        "class": "",
        "title": "",
        "workspace": 1,
        "fullscreen": False,
        "floating": False,
    }
    try:
        proc = subprocess.run(
            ["hyprctl", "activewindow", "-j"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            info["class"] = data.get("class", "")
            info["title"] = data.get("title", "")
            ws = data.get("workspace", {})
            info["workspace"] = ws.get("id", 1) if isinstance(ws, dict) else 1
            info["fullscreen"] = bool(data.get("fullscreen", 0))
            info["floating"] = bool(data.get("floating", False))
    except Exception as e:
        logger.debug("Error leyendo contexto de escritorio: %s", e)

    return info


def get_active_context_summary() -> str:
    """Devuelve un resumen conciso del contexto de pantalla para el LLM."""
    ctx = get_desktop_context()
    app = ctx.get("class", "").strip()
    title = ctx.get("title", "").strip()
    ws = ctx.get("workspace", 1)

    if not app and not title:
        return ""

    parts: list[str] = []
    if title:
        parts.append(f"ventana activa '{title}'")
    if app:
        parts.append(f"aplicacion '{app}'")
    parts.append(f"espacio de trabajo {ws}")
    return ", ".join(parts)


def get_implicit_media_url() -> str:
    """
    Determina la URL de contenido a reproducir o castear:
    1. Si hay una URL en el portapapeles (ej. enlace de YouTube o vídeo).
    2. Si hay una cancion sonando en Navidrome o playerctl.
    """
    # 1. URL en portapapeles
    clip_url = get_clipboard_url()
    if clip_url:
        return clip_url

    # 2. Comprobar reproductor interno de Navidrome
    try:
        from jota.tools.navidrome import get_navidrome_player_status, get_stream_url

        st = get_navidrome_player_status()
        if st and st.get("song_id"):
            return get_stream_url(st["song_id"])
    except Exception:
        pass

    # 3. Comprobar xesam:url de playerctl
    if shutil.which("playerctl"):
        try:
            proc = subprocess.run(
                ["playerctl", "metadata", "xesam:url"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip().startswith("http"):
                return proc.stdout.strip()
        except Exception:
            pass

    return ""


def resolve_device(device_name: str | None = None) -> dict[str, Any]:
    """
    Resuelve el dispositivo de destino segun su alias coloquial
    ('tele', 'salon', 'tv', 'tablet', 'movil').
    Por defecto asume 'tele' si no se especifica.
    """
    clean = (device_name or "tele").lower().strip()
    clean = re.sub(r"^(la|el|al|en\s+la|en\s+el)\s+", "", clean)

    if clean in DEVICES:
        return {"alias": clean, **DEVICES[clean]}

    # Busqueda difusa en el catalogo
    for alias, info in DEVICES.items():
        if alias in clean or clean in info.get("name", "").lower():
            return {"alias": alias, **info}

    # Fallback predeterminado a la television principal
    return {"alias": "tele", **DEVICES.get("tele", {"name": "Android TV Salón", "type": "cast"})}

"""
Operaciones e inspeccion del sistema PC para el bridge.
Permite obtener estado de hardware, captura de pantalla, gestion del portapapeles
y resolucion segura de archivos para transferirlos al dispositivo movil.
"""

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from bridge.config import (
    ALLOWED_ROOT_PATHS,
    FORBIDDEN_PATH_PARTS,
    MAX_FILE_DOWNLOAD_BYTES,
)

logger = logging.getLogger(__name__)


def get_cpu_load() -> dict[str, float]:
    """Obtiene la carga media de CPU del sistema."""
    try:
        load1, load5, load15 = os.getloadavg()
        return {
            "load_1m": round(load1, 2),
            "load_5m": round(load5, 2),
            "load_15m": round(load15, 2),
            "cpu_cores": os.cpu_count() or 1,
        }
    except Exception as e:
        logger.warning("Error al leer carga de CPU: %s", e)
        return {"load_1m": 0.0, "load_5m": 0.0, "load_15m": 0.0, "cpu_cores": 1}


def get_memory_info() -> dict[str, Any]:
    """Obtiene uso de memoria RAM leyendo /proc/meminfo."""
    mem_total_kb = 0
    mem_avail_kb = 0
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_avail_kb = int(line.split()[1])
                if mem_total_kb and mem_avail_kb:
                    break

        if mem_total_kb > 0:
            mem_used_kb = mem_total_kb - mem_avail_kb
            return {
                "total_mb": round(mem_total_kb / 1024, 1),
                "used_mb": round(mem_used_kb / 1024, 1),
                "available_mb": round(mem_avail_kb / 1024, 1),
                "percent_used": round((mem_used_kb / mem_total_kb) * 100, 1),
            }
    except Exception as e:
        logger.warning("Error al leer /proc/meminfo: %s", e)

    return {"total_mb": 0.0, "used_mb": 0.0, "available_mb": 0.0, "percent_used": 0.0}


def get_disk_info() -> dict[str, Any]:
    """Obtiene uso del disco principal del usuario."""
    try:
        usage = shutil.disk_usage(Path.home())
        total_gb = usage.total / (1024**3)
        used_gb = usage.used / (1024**3)
        free_gb = usage.free / (1024**3)
        return {
            "total_gb": round(total_gb, 1),
            "used_gb": round(used_gb, 1),
            "free_gb": round(free_gb, 1),
            "percent_used": round((used_gb / total_gb) * 100, 1),
        }
    except Exception as e:
        logger.warning("Error al leer uso de disco: %s", e)
        return {"total_gb": 0.0, "used_gb": 0.0, "free_gb": 0.0, "percent_used": 0.0}


def get_uptime_seconds() -> int:
    """Obtiene el tiempo encendido del sistema en segundos."""
    try:
        with open("/proc/uptime") as f:
            return int(float(f.read().split()[0]))
    except Exception as e:
        logger.warning("Error al leer /proc/uptime: %s", e)
        return 0


def get_active_window_info() -> dict[str, Any]:
    """Obtiene la ventana activa en Hyprland mediante hyprctl."""
    try:
        result = subprocess.run(
            ["hyprctl", "activewindow", "-j"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            return {
                "class": data.get("class", ""),
                "title": data.get("title", ""),
                "workspace": data.get("workspace", {}).get("name", ""),
            }
    except Exception as e:
        logger.debug("hyprctl activewindow no disponible: %s", e)

    return {"class": "", "title": "", "workspace": ""}


def get_system_status() -> dict[str, Any]:
    """Retorna un resumen completo del estado del PC."""
    return {
        "cpu": get_cpu_load(),
        "memory": get_memory_info(),
        "disk": get_disk_info(),
        "uptime_seconds": get_uptime_seconds(),
        "active_window": get_active_window_info(),
    }


def capture_screen_bytes() -> bytes:
    """
    Captura la pantalla actual en Wayland usando grim y retorna los bytes PNG.
    Lanza RuntimeError si grim falla o no esta disponible.
    """
    cmd = ["grim", "-"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"grim fallo con codigo {result.returncode}: {err}")
        return result.stdout
    except FileNotFoundError:
        raise RuntimeError("El binario 'grim' no se encuentra instalado en el sistema.")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Tiempo de espera agotado al capturar la pantalla.")


def get_clipboard_text() -> str:
    """
    Lee el portapapeles actual de Wayland usando wl-paste.
    Si esta vacio o no hay texto disponible, retorna cadena vacia.
    """
    try:
        result = subprocess.run(
            ["wl-paste", "--no-newline"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
        return ""
    except Exception as e:
        logger.debug("Error leyendo portapapeles con wl-paste: %s", e)
        return ""


def set_clipboard_text(text: str) -> bool:
    """
    Copia texto al portapapeles de Wayland usando wl-copy sin bloquear el proceso.
    """
    try:
        proc = subprocess.Popen(
            ["wl-copy"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        proc.communicate(input=text.encode("utf-8"), timeout=2)
        return True
    except Exception as e:
        logger.warning("Error escribiendo en portapapeles con wl-copy: %s", e)
        return False


def resolve_safe_file_path(requested_path: str) -> Path:
    """
    Resuelve y valida que la ruta solicitada sea segura para descargar.
    Evita directory traversal y acceso a carpetas privadas del sistema.

    Lanza ValueError si la ruta es invalida o insegura.
    Lanza FileNotFoundError si el archivo no existe.
    """
    if not requested_path or not requested_path.strip():
        raise ValueError("Ruta de archivo vacia.")

    # Expandir tilde y resolver ruta canonica absoluta
    raw_path = Path(os.path.expanduser(requested_path.strip()))
    try:
        resolved = raw_path.resolve(strict=True)
    except FileNotFoundError:
        raise FileNotFoundError(f"El archivo no existe: {requested_path}")

    # Validar que sea un archivo regular
    if not resolved.is_file():
        raise ValueError(f"La ruta indicada no es un archivo regular: {requested_path}")

    # Validar que este dentro de una raiz permitida
    is_under_allowed_root = any(
        resolved == root or root in resolved.parents for root in ALLOWED_ROOT_PATHS
    )
    if not is_under_allowed_root:
        raise ValueError(
            f"Acceso denegado: ruta fuera de las raices autorizadas ({requested_path})"
        )

    # Validar contra patrones prohibidos
    path_str = str(resolved)
    for forbidden in FORBIDDEN_PATH_PARTS:
        if forbidden in path_str:
            raise ValueError(f"Acceso denegado a archivo protegido ({forbidden})")

    # Validar tamano maximo
    file_size = resolved.stat().st_size
    if file_size > MAX_FILE_DOWNLOAD_BYTES:
        max_mb = MAX_FILE_DOWNLOAD_BYTES // (1024 * 1024)
        raise ValueError(f"El archivo excede el limite maximo permitido de {max_mb} MB.")

    return resolved

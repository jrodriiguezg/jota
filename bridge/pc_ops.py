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
from datetime import datetime
from pathlib import Path
from typing import Any

from bridge.config import (
    ALLOWED_ROOT_PATHS,
    FORBIDDEN_PATH_PARTS,
    HOME_PATH,
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


def get_battery_status() -> dict[str, Any]:
    """Obtiene el estado de la bateria del PC (portatil) si existe."""
    power_supply = Path("/sys/class/power_supply")
    if not power_supply.exists():
        return {"present": False, "percent": None, "charging": False, "status": "unknown"}

    try:
        bat_dirs = sorted(list(power_supply.glob("BAT*")))
        if not bat_dirs:
            return {"present": False, "percent": None, "charging": False, "status": "no_battery"}

        bat = bat_dirs[0]
        cap_file = bat / "capacity"
        stat_file = bat / "status"

        percent = int(cap_file.read_text().strip()) if cap_file.exists() else None
        status_text = stat_file.read_text().strip() if stat_file.exists() else "unknown"
        charging = status_text.lower() in ("charging", "cargando")

        return {
            "present": True,
            "percent": percent,
            "charging": charging,
            "status": status_text,
        }
    except Exception as e:
        logger.debug("Error leyendo estado de bateria del PC: %s", e)
        return {"present": False, "percent": None, "charging": False, "status": "error"}


def get_media_status() -> dict[str, Any]:
    """Obtiene informacion detallada de la reproduccion multimedia actual (MPRIS)."""
    empty_media = {
        "player": "",
        "title": "",
        "artist": "",
        "album": "",
    }
    if not shutil.which("playerctl"):
        return {"available": False, "status": "unavailable", **empty_media}

    try:
        proc_status = subprocess.run(
            ["playerctl", "status"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if proc_status.returncode != 0 or not proc_status.stdout.strip():
            return {"available": True, "status": "Stopped", **empty_media}

        status = proc_status.stdout.strip()
        format_str = "{{playerName}}\t{{title}}\t{{artist}}\t{{album}}"
        proc_meta = subprocess.run(
            ["playerctl", "metadata", "--format", format_str],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )

        player, title, artist, album = "", "", "", ""
        if proc_meta.returncode == 0 and proc_meta.stdout.strip():
            parts = proc_meta.stdout.strip().split("\t")
            if len(parts) >= 1:
                player = parts[0]
            if len(parts) >= 2:
                title = parts[1]
            if len(parts) >= 3:
                artist = parts[2]
            if len(parts) >= 4:
                album = parts[3]

        return {
            "available": True,
            "status": status,
            "player": player,
            "title": title,
            "artist": artist,
            "album": album,
        }
    except Exception as e:
        logger.debug("Error al leer estado multimedia: %s", e)
        return {"available": False, "status": "error", **empty_media}


def get_system_status() -> dict[str, Any]:
    """Retorna un resumen completo del estado del PC."""
    return {
        "cpu": get_cpu_load(),
        "memory": get_memory_info(),
        "disk": get_disk_info(),
        "uptime_seconds": get_uptime_seconds(),
        "active_window": get_active_window_info(),
        "battery": get_battery_status(),
        "media": get_media_status(),
    }


SCREENSHOTS_DIR = Path.home() / ".local" / "share" / "jota" / "screenshots"


def capture_screen_bytes(
    save_history: bool = True,
    format: str = "png",
    quality: int = 80,
    scale: float = 1.0,
) -> bytes:
    """
    Captura la pantalla actual en Wayland usando grim y retorna los bytes solicitados.
    Soporta formatos 'png' (por defecto) o 'jpeg'/'jpg' comprimido con ImageMagick (magick/convert).
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

        raw_png_bytes = result.stdout
        if not raw_png_bytes:
            raise RuntimeError("grim retorno una captura vacia.")

        if save_history:
            try:
                SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                (SCREENSHOTS_DIR / f"screenshot_{ts}.png").write_bytes(raw_png_bytes)
            except Exception as e:
                logger.warning("No se pudo guardar copia de captura en historial: %s", e)

        # Si se solicita formato JPEG / JPG optimizado para red movil
        clean_fmt = format.lower().strip()
        if clean_fmt in ("jpeg", "jpg"):
            magick_bin = shutil.which("magick") or shutil.which("convert")
            if magick_bin:
                conv_args = [magick_bin, "-"]
                if 0.1 <= scale < 1.0:
                    conv_args.extend(["-resize", f"{int(scale * 100)}%"])
                conv_args.extend(["-quality", str(max(10, min(100, quality))), "jpg:-"])

                conv_res = subprocess.run(
                    conv_args,
                    input=raw_png_bytes,
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
                if conv_res.returncode == 0 and conv_res.stdout:
                    logger.debug(
                        "Captura convertida a JPEG (calidad %d): %d -> %d bytes",
                        quality,
                        len(raw_png_bytes),
                        len(conv_res.stdout),
                    )
                    return conv_res.stdout

        return raw_png_bytes
    except FileNotFoundError:
        raise RuntimeError("El binario 'grim' no se encuentra instalado en el sistema.")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Tiempo de espera agotado al capturar la pantalla.")


def get_pc_screenshots(limit: int = 50) -> list[dict[str, Any]]:
    """
    Retorna la lista de capturas de pantalla disponibles en el PC,
    ordenadas cronologicamente desde la mas reciente.
    """
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    scan_dirs = [
        SCREENSHOTS_DIR,
        Path.home() / "Imágenes" / "Capturas",
        Path.home() / "Pictures" / "Screenshots",
        Path.home() / "Imágenes",
        Path.home() / "Pictures",
    ]
    seen_paths = set()
    results: list[dict[str, Any]] = []

    for s_dir in scan_dirs:
        if not s_dir.exists():
            continue
        for ext in ("*.png", "*.jpg", "*.jpeg"):
            for f in s_dir.glob(ext):
                if not f.is_file() or f in seen_paths:
                    continue
                seen_paths.add(f)
                name_lower = f.name.lower()
                # En directorios genericos de Imagenes, filtrar solo aquellas que sean capturas
                if s_dir in (Path.home() / "Imágenes", Path.home() / "Pictures"):
                    if not any(
                        k in name_lower for k in ("screenshot", "captura", "hyprshot", "grim")
                    ):
                        continue

                try:
                    stat = f.stat()
                    dt = datetime.fromtimestamp(stat.st_mtime)
                    try:
                        rel = str(f.relative_to(Path.home()))
                    except ValueError:
                        rel = str(f)
                    results.append(
                        {
                            "id": f.name,
                            "filename": f.name,
                            "relative_path": rel,
                            "size_bytes": stat.st_size,
                            "timestamp": int(stat.st_mtime),
                            "date_str": dt.strftime("%Y-%m-%d %H:%M:%S"),
                        }
                    )
                except Exception as e:
                    logger.debug("Error procesando imagen %s: %s", f, e)

    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return results[:limit]


def resolve_screenshot_file(query: str) -> Path | None:
    """
    Localiza y valida con seguridad una captura de pantalla especifica solicitada.
    """
    clean = query.strip()
    if not clean:
        return None

    # 1. Si es ruta relativa dentro del HOME
    direct = (Path.home() / clean).resolve()
    if direct.is_file() and str(direct).startswith(str(Path.home())):
        return direct

    # 2. Buscar por nombre directo en directorios de capturas
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    candidates = [
        SCREENSHOTS_DIR / clean,
        Path.home() / "Imágenes" / "Capturas" / clean,
        Path.home() / "Pictures" / "Screenshots" / clean,
        Path.home() / "Imágenes" / clean,
        Path.home() / "Pictures" / clean,
    ]
    for c in candidates:
        if c.is_file():
            return c

    # 3. Coincidencia parcial
    for s_dir in [
        SCREENSHOTS_DIR,
        Path.home() / "Imágenes" / "Capturas",
        Path.home() / "Imágenes",
    ]:
        if s_dir.exists():
            for f in s_dir.glob("*.png"):
                if clean in f.name:
                    return f

    return None


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
    Evita directory traversal, inyecciones de bytes nulos y acceso a carpetas privadas del sistema.

    Lanza ValueError si la ruta es invalida o insegura.
    Lanza FileNotFoundError si el archivo no existe.
    """
    if not requested_path or not requested_path.strip():
        raise ValueError("Ruta de archivo vacia.")

    # Proteccion contra inyeccion de byte nulo
    if "\x00" in requested_path:
        raise ValueError("Caracter nulo invalido detectado en la ruta.")

    # Expandir tilde y resolver ruta canonica
    clean_str = os.path.expanduser(requested_path.strip())
    raw_path = Path(clean_str)

    if not raw_path.is_absolute():
        candidate = (HOME_PATH / raw_path).resolve()
        if not candidate.is_file():
            cwd_cand = (Path.cwd() / raw_path).resolve()
            if cwd_cand.is_file():
                candidate = cwd_cand
            else:
                candidate = (SCREENSHOTS_DIR / clean_str).resolve()
        resolved = candidate
    else:
        resolved = raw_path.resolve()

    if not resolved.is_file():
        raise FileNotFoundError(f"El archivo no existe: {requested_path}")

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


def execute_pc_action(action: str) -> tuple[bool, str]:
    """
    Ejecuta una accion rapida en el PC sin requerir transcripcion de voz.
    Soporta: lock, mute, vol_up, vol_down, play_pause, next, previous.
    """
    from jota.tools.media import playback_control, set_volume, toggle_mute

    clean_act = action.lower().strip()
    if clean_act == "lock":
        try:
            subprocess.Popen(["hyprlock"])
            return True, "Sesion bloqueada."
        except FileNotFoundError:
            subprocess.Popen(["loginctl", "lock-session"])
            return True, "Sesion bloqueada."
        except Exception as e:
            return False, f"Error al bloquear sesion: {e}"

    if clean_act == "mute":
        return toggle_mute()
    if clean_act in ("vol_up", "up", "volume_up"):
        return set_volume("up")
    if clean_act in ("vol_down", "down", "volume_down"):
        return set_volume("down")
    if clean_act.startswith("vol_set:") or clean_act.startswith("volume_set:"):
        val_str = clean_act.split(":", 1)[1].strip()
        try:
            from jota.tools.media import set_volume_level
            return set_volume_level(int(val_str))
        except ValueError:
            return False, f"Nivel de volumen invalido: {val_str}"
    if clean_act in ("play_pause", "toggle_playback"):
        return playback_control("play_pause")
    if clean_act in ("next", "next_track"):
        return playback_control("next")
    if clean_act in ("previous", "prev", "prev_track"):
        return playback_control("previous")

    if clean_act.startswith("open_url:"):
        url = action.split(":", 1)[1].strip()
        try:
            subprocess.Popen(["xdg-open", url])
            return True, f"Abriendo enlace en el navegador: {url}"
        except Exception as e:
            return False, f"Error al abrir URL: {e}"

    if clean_act.startswith("check_package:") or clean_act.startswith("pkg:"):
        parts = action.split(":")
        pkg_name = parts[1].strip() if len(parts) > 1 else ""
        check_type = parts[2].strip() if len(parts) > 2 else "version"
        from jota.tools.packages import check_package
        return check_package(pkg_name, check=check_type)

    return False, f"Accion no reconocida: {action}"


def get_pc_network_info() -> dict[str, Any]:
    """
    Obtiene la informacion de red del PC (hostname, interfaces, direcciones MAC para Wake-on-LAN).
    """
    import glob
    import socket

    hostname = socket.gethostname()
    interfaces: list[dict[str, str]] = []
    primary_mac = ""

    for iface_path in sorted(glob.glob("/sys/class/net/*")):
        iface_name = os.path.basename(iface_path)
        if iface_name == "lo" or iface_name.startswith("docker"):
            continue
        try:
            addr_file = os.path.join(iface_path, "address")
            state_file = os.path.join(iface_path, "operstate")
            mac = ""
            state = "unknown"
            if os.path.isfile(addr_file):
                with open(addr_file) as f:
                    mac = f.read().strip()
            if os.path.isfile(state_file):
                with open(state_file) as f:
                    state = f.read().strip()

            if mac and len(mac) == 17:
                interfaces.append({
                    "name": iface_name,
                    "mac": mac,
                    "state": state,
                })
                if state == "up" and not primary_mac:
                    primary_mac = mac
        except Exception as e:
            logger.debug("Error leyendo interfaz %s: %s", iface_name, e)

    if not primary_mac and interfaces:
        primary_mac = interfaces[0]["mac"]

    return {
        "hostname": hostname,
        "primary_mac": primary_mac,
        "interfaces": interfaces,
    }


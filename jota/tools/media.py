"""Control multimedia de audio y reproduccion (PipeWire/WirePlumber y playerctl)."""

import logging
import re
import shutil
import subprocess

from jota.config import VOLUME_STEP_PERCENT

logger = logging.getLogger(__name__)


def _run_cmd(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Ejecuta un comando de sistema de forma segura."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )


def get_current_volume() -> int | None:
    """Obtiene el volumen actual en porcentaje (0-100+) usando wpctl."""
    if not shutil.which("wpctl"):
        return None

    proc = _run_cmd(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
    if proc.returncode == 0 and proc.stdout:
        # Formato habitual: "Volume: 0.85" o "Volume: 0.85 [MUTED]"
        match = re.search(r"Volume:\s+([0-9.]+)", proc.stdout)
        if match:
            try:
                val = float(match.group(1))
                return int(round(val * 100))
            except ValueError:
                pass
    return None


def is_muted() -> bool | None:
    """Indica si el audio esta silenciado."""
    if not shutil.which("wpctl"):
        return None

    proc = _run_cmd(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
    if proc.returncode == 0:
        return "[MUTED]" in proc.stdout
    return None


def set_volume(direction: str, step: int = VOLUME_STEP_PERCENT) -> tuple[bool, str]:
    """
    Sube o baja el volumen del sistema.
    direction: 'up' | 'down'
    """
    sign = "+" if direction == "up" else "-"
    verb = "subido" if direction == "up" else "bajado"

    # Intentar con wpctl (PipeWire / WirePlumber por defecto en Fedora)
    if shutil.which("wpctl"):
        res = _run_cmd([
            "wpctl",
            "set-volume",
            "-l",
            "1.5",
            "@DEFAULT_AUDIO_SINK@",
            f"{step}%{sign}",
        ])
        if res.returncode == 0:
            vol = get_current_volume()
            msg = f"Volumen {verb} al {vol}%." if vol is not None else f"Volumen {verb}."
            logger.info("Control de volumen: %s", msg)
            return True, msg

    # Fallback con pactl
    if shutil.which("pactl"):
        res = _run_cmd(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{sign}{step}%"])
        if res.returncode == 0:
            msg = f"Volumen {verb}."
            logger.info("Control de volumen via pactl: %s", msg)
            return True, msg

    err_msg = "No se encontro ningun controlador de volumen compatible (wpctl/pactl)."
    logger.error(err_msg)
    return False, err_msg


def set_volume_level(level: int) -> tuple[bool, str]:
    """
    Ajusta el volumen del sistema a un porcentaje especifico (0-150).
    """
    clamped = max(0, min(150, int(level)))

    # Intentar con wpctl (PipeWire / WirePlumber por defecto en Fedora)
    if shutil.which("wpctl"):
        res = _run_cmd([
            "wpctl",
            "set-volume",
            "-l",
            "1.5",
            "@DEFAULT_AUDIO_SINK@",
            f"{clamped}%",
        ])
        if res.returncode == 0:
            vol = get_current_volume()
            target_vol = vol if vol is not None else clamped
            msg = f"Volumen fijado al {target_vol}%."
            logger.info("Control de volumen: %s", msg)
            return True, msg

    # Fallback con pactl
    if shutil.which("pactl"):
        res = _run_cmd(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{clamped}%"])
        if res.returncode == 0:
            msg = f"Volumen fijado al {clamped}%."
            logger.info("Control de volumen via pactl: %s", msg)
            return True, msg

    err_msg = "No se encontro ningun controlador de volumen compatible (wpctl/pactl)."
    logger.error(err_msg)
    return False, err_msg


def toggle_mute() -> tuple[bool, str]:
    """Alterna el silencio de audio del sistema."""
    if shutil.which("wpctl"):
        res = _run_cmd(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"])
        if res.returncode == 0:
            muted = is_muted()
            msg = "Audio silenciado." if muted else "Audio activado."
            logger.info("Silencio de audio: %s", msg)
            return True, msg

    if shutil.which("pactl"):
        res = _run_cmd(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
        if res.returncode == 0:
            return True, "Silencio de audio alternado."

    return False, "No se pudo cambiar el estado de silencio."


def playback_control(action: str) -> tuple[bool, str]:
    """
    Controla la reproduccion de reproductores MPRIS via playerctl.
    action: 'play' | 'pause' | 'play_pause' | 'next' | 'previous' | 'stop'
    """
    if not shutil.which("playerctl"):
        return False, "playerctl no esta instalado en el sistema."

    actions_map = {
        "play": ("play", "Reproduciendo musica."),
        "pause": ("pause", "Musica pausada."),
        "play_pause": ("play-pause", "Reproduccion alternada."),
        "toggle": ("play-pause", "Reproduccion alternada."),
        "next": ("next", "Siguiente cancion."),
        "previous": ("previous", "Cancion anterior."),
        "stop": ("stop", "Reproduccion detenida."),
    }

    if action not in actions_map:
        return False, f"Accion de reproduccion no reconocida: {action}"

    cmd_action, ok_message = actions_map[action]
    res = _run_cmd(["playerctl", cmd_action])

    if res.returncode == 0:
        logger.info("Reproduccion multimedia: %s", ok_message)
        return True, ok_message

    # Si playerctl falla en reproducir porque no hay reproductor abierto,
    # intentar abrir el predeterminado
    if action in ("play", "play_pause", "toggle"):
        try:
            from jota.tools.apps import launch_application
            ok, msg = launch_application("musica")
            if ok:
                return True, "Iniciando reproductor de musica."
        except Exception as e:
            logger.debug("Error al lanzar reproductor como fallback: %s", e)

    # Si playerctl falla porque no hay reproductores
    logger.warning("Fallo en playerctl %s: %s", cmd_action, res.stderr.strip())
    return False, "No hay ningun reproductor multimedia activo."



def get_now_playing() -> tuple[bool, str]:
    """Consulta la cancion o pista multimedia que esta sonando actualmente."""
    if not shutil.which("playerctl"):
        return False, "playerctl no esta instalado en el sistema."

    try:
        format_str = "{{playerName}}\t{{title}}\t{{artist}}"
        proc = _run_cmd(["playerctl", "metadata", "--format", format_str])
        if proc.returncode == 0 and proc.stdout.strip():
            parts = proc.stdout.strip().split("\t")
            player = parts[0] if len(parts) >= 1 else ""
            title = parts[1] if len(parts) >= 2 else ""
            artist = parts[2] if len(parts) >= 3 else ""

            if title and artist:
                msg = f"Esta sonando {title} de {artist}."
            elif title:
                msg = f"Esta sonando {title}."
            else:
                msg = f"Reproduciendo contenido en {player}."

            return True, msg
        return True, "No hay ninguna pista reproduciendose en este momento."
    except Exception as e:
        logger.debug("Error leyendo cancion actual: %s", e)
        return False, "No se pudo obtener informacion de la cancion."


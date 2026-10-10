"""
Control de dispositivos y televisor mediante HDMI-CEC (cec-client).
Permite encender, apagar y conmutar la entrada HDMI de la pantalla.
"""

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


def cec_control(action: str, target: str = "tele") -> tuple[bool, str]:
    """
    Ejecuta comandos HDMI-CEC sobre la pantalla o televisor.
    Acciones soportadas: 'turn_on', 'turn_off', 'standby', 'switch', 'source'.
    """
    clean_action = action.lower().strip()

    if not shutil.which("cec-client"):
        return False, "cec-client no esta instalado en el sistema."

    commands = {
        "turn_on": ("on 0", "Encendiendo la television."),
        "on": ("on 0", "Encendiendo la television."),
        "turn_off": ("standby 0", "Apagando la television."),
        "standby": ("standby 0", "Apagando la television."),
        "off": ("standby 0", "Apagando la television."),
        "switch": ("as", "Cambiando entrada HDMI a este equipo."),
        "source": ("as", "Cambiando entrada HDMI a este equipo."),
        "as": ("as", "Cambiando entrada HDMI a este equipo."),
    }

    if clean_action not in commands:
        return False, f"Accion HDMI-CEC no reconocida: {action}"

    cec_cmd, success_msg = commands[clean_action]

    try:
        proc = subprocess.run(
            ["cec-client", "-s", "-d", "1"],
            input=cec_cmd,
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        if proc.returncode == 0:
            return True, success_msg
        logger.warning("cec-client devolvio codigo %d: %s", proc.returncode, proc.stderr)
        return False, "No se pudo comunicar con el dispositivo HDMI-CEC."
    except subprocess.TimeoutExpired:
        logger.error("Tiempo de espera agotado ejecutando cec-client.")
        return False, "Tiempo de espera agotado al comunicar por HDMI-CEC."
    except Exception as e:
        logger.error("Error al ejecutar cec-client: %s", e)
        return False, f"Error al ejecutar comando HDMI-CEC: {e}"

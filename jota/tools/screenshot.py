"""Herramienta para captura de pantalla y copia directa al portapapeles (Wayland / Hyprland)."""

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


def take_screenshot_to_clipboard() -> tuple[bool, str]:
    """
    Captura la pantalla completa usando grim y la copia al portapapeles con wl-copy.
    Devuelve (exito, mensaje_para_tts).
    """
    grim_bin = shutil.which("grim")
    wl_copy_bin = shutil.which("wl-copy")

    if not grim_bin or not wl_copy_bin:
        err_msg = "Se requieren 'grim' y 'wl-copy' para capturar la pantalla en Wayland."
        logger.error(err_msg)
        return False, "No se encontraron las utilidades de captura de pantalla en el sistema."

    try:
        # Tomar captura a stdout
        grim_proc = subprocess.run(
            [grim_bin, "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )

        if grim_proc.returncode != 0 or not grim_proc.stdout:
            logger.error("grim fallo con codigo de salida %d", grim_proc.returncode)
            return False, "Ocurrio un error al capturar la pantalla."

        # Copiar imagen al portapapeles sin bloquear el proceso daemonizado
        copy_proc = subprocess.run(
            [wl_copy_bin, "--type", "image/png"],
            input=grim_proc.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )

        if copy_proc.returncode == 0:
            msg = "Captura de pantalla copiada al portapapeles."
            logger.info(msg)
            return True, msg

        logger.error("wl-copy fallo con codigo de salida %d", copy_proc.returncode)
        return False, "No se pudo copiar la captura al portapapeles."

    except subprocess.TimeoutExpired:
        logger.error("Tiempo de espera agotado al capturar la pantalla.")
        return False, "La captura de pantalla tardo demasiado tiempo."
    except Exception as exc:
        logger.exception("Excepcion inesperada en captura de pantalla: %s", exc)
        return False, "Fallo inesperado al realizar la captura."

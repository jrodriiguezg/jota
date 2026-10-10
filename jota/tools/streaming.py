"""
Herramientas de streaming y pantalla remota para Jota.
Incluye visualizacion del movil con scrcpy, monitores headless en Hyprland
y segunda pantalla en tablet mediante wayvnc.
"""

import logging
import shutil
import subprocess

from jota.config import DEVICES

logger = logging.getLogger(__name__)

_tablet_vnc_proc: subprocess.Popen | None = None
_active_headless_output: str | None = None


def open_phone_screen(serial: str | None = None) -> tuple[bool, str]:
    """
    Abre la pantalla del telefono movil en el escritorio de Hyprland usando scrcpy.
    """
    if not shutil.which("scrcpy"):
        return (
            False,
            "scrcpy no esta instalado. Puedes instalarlo con 'sudo dnf install scrcpy'.",
        )

    phone_serial = serial or DEVICES.get("movil", {}).get("serial")

    cmd = ["scrcpy", "--window-title", "Jota - Telefono"]
    if phone_serial:
        cmd.extend(["-s", phone_serial])

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True, "Mostrando la pantalla del movil en el escritorio."
    except Exception as e:
        logger.error("Error al iniciar scrcpy: %s", e)
        return False, f"Error al abrir la pantalla del movil: {e}"


def create_headless_display(output_name: str | None = None) -> tuple[bool, str]:
    """
    Crea una salida virtual headless en Hyprland para duplicacion o extension.
    """
    if not shutil.which("hyprctl"):
        return False, "hyprctl no esta disponible en el sistema."

    try:
        cmd = ["hyprctl", "output", "create", "headless"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3, check=False)
        if proc.returncode == 0:
            out_name = proc.stdout.strip() or (output_name or "HEADLESS-1")
            global _active_headless_output
            _active_headless_output = out_name
            return True, f"Monitor virtual headless '{out_name}' creado."
        return False, f"No se pudo crear la salida headless: {proc.stderr.strip()}"
    except Exception as e:
        logger.error("Error al crear monitor headless: %s", e)
        return False, f"Fallo al crear monitor headless: {e}"


def remove_headless_display(output_name: str | None = None) -> tuple[bool, str]:
    """
    Elimina una salida virtual headless previamente creada en Hyprland.
    """
    if not shutil.which("hyprctl"):
        return False, "hyprctl no esta disponible en el sistema."

    global _active_headless_output
    target = output_name or _active_headless_output or "HEADLESS-1"

    try:
        cmd = ["hyprctl", "output", "remove", target]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3, check=False)
        if proc.returncode == 0:
            if _active_headless_output == target:
                _active_headless_output = None
            return True, f"Monitor virtual headless '{target}' eliminado."
        return False, f"No se pudo eliminar el monitor headless: {proc.stderr.strip()}"
    except Exception as e:
        logger.error("Error al eliminar monitor headless: %s", e)
        return False, f"Fallo al eliminar monitor headless: {e}"


def start_tablet_display(action: str = "start") -> tuple[bool, str]:
    """
    Inicia o detiene la proyeccion hacia la tablet mediante wayvnc y Hyprland headless.
    """
    global _tablet_vnc_proc, _active_headless_output

    if action in ("stop", "detener", "apagar"):
        if _tablet_vnc_proc and _tablet_vnc_proc.poll() is None:
            _tablet_vnc_proc.terminate()
            _tablet_vnc_proc = None

        if _active_headless_output:
            remove_headless_display(_active_headless_output)

        return True, "Segunda pantalla para la tablet detenida."

    # Iniciar proyeccion a tablet
    if not shutil.which("wayvnc"):
        return (
            False,
            "wayvnc no esta instalado. Puedes instalarlo con 'sudo dnf install wayvnc' "
            "para usar la tablet como segunda pantalla.",
        )

    ok, msg = create_headless_display()
    if not ok:
        return False, f"No se pudo inicializar la pantalla para la tablet: {msg}"

    headless_name = _active_headless_output or "HEADLESS-1"
    try:
        cmd = ["wayvnc", "--output", headless_name, "0.0.0.0", "5900"]
        _tablet_vnc_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return (
            True,
            "Segunda pantalla para tablet lista. Conectate por VNC al puerto 5900.",
        )
    except Exception as e:
        logger.error("Error al arrancar wayvnc: %s", e)
        return False, f"Error al iniciar servidor de pantalla remota: {e}"

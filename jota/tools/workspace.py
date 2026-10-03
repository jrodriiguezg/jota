"""Control de workspaces y ventanas en Hyprland."""

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


def switch_workspace(workspace_id: int | str) -> tuple[bool, str]:
    """Cambia el espacio de trabajo activo en Hyprland."""
    hyprctl = shutil.which("hyprctl")
    if not hyprctl:
        return False, "hyprctl no esta disponible en este entorno."

    target = str(workspace_id).strip()
    try:
        res = subprocess.run(
            [hyprctl, "dispatch", "workspace", target],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            return True, f"Cambiado al espacio de trabajo {target}."
        return False, f"Fallo al cambiar de espacio de trabajo: {res.stderr.strip()}"
    except Exception as e:
        logger.error("Error al cambiar workspace: %s", e)
        return False, f"Error al cambiar espacio de trabajo: {e}"


def move_to_workspace(workspace_id: int | str) -> tuple[bool, str]:
    """Mueve la ventana en foco al espacio de trabajo indicado."""
    hyprctl = shutil.which("hyprctl")
    if not hyprctl:
        return False, "hyprctl no esta disponible en este entorno."

    target = str(workspace_id).strip()
    try:
        res = subprocess.run(
            [hyprctl, "dispatch", "movetoworkspace", target],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            return True, f"Ventana movida al espacio de trabajo {target}."
        return False, f"Fallo al mover ventana: {res.stderr.strip()}"
    except Exception as e:
        logger.error("Error al mover ventana a workspace: %s", e)
        return False, f"Error al mover ventana: {e}"

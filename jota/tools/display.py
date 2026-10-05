"""
Herramientas de control de pantalla, brillo y filtro de luz azul (modo noche).
Compatible con Wayland / Hyprland usando brightnessctl, hyprsunset, wlsunset o gammastep.
"""

import logging
import re
import shutil
import subprocess

logger = logging.getLogger(__name__)


def brightness_control(
    percent: int | str | None = None, action: str = "set"
) -> tuple[bool, str]:
    """
    Controla el brillo de la pantalla usando brightnessctl.
    percent: nivel de brillo de 0 a 100
    action: 'set' | 'up' | 'down' | 'get'
    """
    b_bin = shutil.which("brightnessctl")
    if not b_bin:
        return False, "brightnessctl no esta instalado en el sistema."

    clean_act = str(action).lower().strip()

    try:
        if clean_act in ("up", "subir", "mas"):
            subprocess.run([b_bin, "set", "+10%"], capture_output=True, text=True, check=True)
        elif clean_act in ("down", "bajar", "menos"):
            subprocess.run([b_bin, "set", "10%-"], capture_output=True, text=True, check=True)
        elif percent is not None:
            pct_val = int(re.sub(r"[^\d]", "", str(percent)) or "50")
            pct_val = max(1, min(100, pct_val))
            subprocess.run(
                [b_bin, "set", f"{pct_val}%"],
                capture_output=True,
                text=True,
                check=True,
            )

        # Leer porcentaje actual con brightnessctl -m
        res = subprocess.run([b_bin, "-m"], capture_output=True, text=True, check=False)
        cur_pct = "50"
        if res.returncode == 0 and res.stdout.strip():
            # Formato: device,class,curr,curr%,max
            parts = res.stdout.strip().splitlines()[0].split(",")
            if len(parts) >= 4:
                cur_pct = parts[3].replace("%", "").strip()

        if clean_act in ("get", "consultar"):
            return True, f"El brillo actual de la pantalla es del {cur_pct}%."

        return True, f"Brillo de la pantalla ajustado al {cur_pct}%."
    except Exception as e:
        logger.error("Error ajustando brillo: %s", e)
        return False, f"Error al cambiar el brillo: {e}"


def night_mode_control(action: str = "toggle") -> tuple[bool, str]:
    """
    Controla el filtro de luz azul (modo noche).
    Soporta hyprsunset, wlsunset y gammastep.
    action: 'on' | 'off' | 'toggle'
    """
    clean_act = str(action).lower().strip()

    # Detectar binario disponible
    daemon_bin = (
        shutil.which("hyprsunset")
        or shutil.which("wlsunset")
        or shutil.which("gammastep")
    )

    # Comprobar si hay algun demonio de luz azul en ejecucion
    is_running = False
    active_daemon = None
    for name in ("hyprsunset", "wlsunset", "gammastep"):
        pcheck = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True, check=False)
        if pcheck.returncode == 0:
            is_running = True
            active_daemon = name
            break

    turn_off = clean_act in ("off", "desactivar", "quitar", "apagar") or (
        clean_act in ("toggle", "cambiar") and is_running
    )

    if turn_off:
        if is_running and active_daemon:
            subprocess.run(["pkill", "-x", active_daemon], capture_output=True, check=False)
            return True, "Filtro de luz azul desactivado."
        return True, "El filtro de luz azul ya esta desactivado."

    # Encender modo noche
    if is_running:
        return True, "El filtro de luz azul ya esta activo."

    if not daemon_bin:
        return (
            False,
            "No se encontro hyprsunset, wlsunset ni gammastep instalados. "
            "Puedes instalarlo con 'sudo dnf install wlsunset'.",
        )

    try:
        bin_name = daemon_bin.split("/")[-1]
        if bin_name == "hyprsunset":
            cmd = [daemon_bin, "-t", "4000"]
        elif bin_name == "wlsunset":
            cmd = [daemon_bin, "-t", "4000", "-T", "6500"]
        else:
            cmd = [daemon_bin, "-O", "4000"]

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True, "Modo noche activado con temperatura de 4000 Kelvin."
    except Exception as e:
        logger.error("Error activando modo noche: %s", e)
        return False, f"Error al activar modo noche: {e}"

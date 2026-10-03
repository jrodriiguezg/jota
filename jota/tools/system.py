"""
Herramientas de control del sistema para Jota:
Bloqueo de sesion, control de energia, notificaciones de escritorio,
gestion de ventanas Hyprland y resumen del estado del equipo.
"""

import json
import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


def lock_pc() -> tuple[bool, str]:
    """Bloquea la sesion actual del escritorio."""
    logger.info("Bloqueando sesion del PC...")
    try:
        subprocess.Popen(["hyprlock"])
        return True, "Sesion bloqueada."
    except FileNotFoundError:
        try:
            subprocess.Popen(["loginctl", "lock-session"])
            return True, "Sesion bloqueada."
        except Exception as e:
            return False, f"No se pudo bloquear la sesion: {e}"
    except Exception as e:
        return False, f"Error al ejecutar hyprlock: {e}"


def system_power(action: str) -> tuple[bool, str]:
    """
    Gestiona el estado de energia del PC:
    suspend, reboot, poweroff.
    """
    clean_action = action.lower().strip()
    logger.info("system_power llamado con accion: '%s'", clean_action)

    if clean_action in ("suspend", "suspender", "dormir", "suspension"):
        try:
            subprocess.Popen(["systemctl", "suspend"])
            return True, "Suspendiendo el equipo."
        except Exception as e:
            return False, f"Fallo al suspender: {e}"

    if clean_action in ("reboot", "reiniciar", "reinicia"):
        try:
            subprocess.Popen(["systemctl", "reboot"])
            return True, "Reiniciando el sistema."
        except Exception as e:
            return False, f"Fallo al reiniciar: {e}"

    if clean_action in ("poweroff", "apagar", "apaga"):
        try:
            subprocess.Popen(["systemctl", "poweroff"])
            return True, "Apagando el equipo."
        except Exception as e:
            return False, f"Fallo al apagar: {e}"

    return False, f"Accion de energia '{action}' no soportada."


def close_active_window() -> tuple[bool, str]:
    """Cierra la ventana activa en Hyprland."""
    logger.info("Cerrando ventana activa en Hyprland...")
    try:
        res = subprocess.run(
            ["hyprctl", "dispatch", "killactive"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if res.returncode == 0:
            return True, "Ventana cerrada."
        return False, "No se pudo cerrar la ventana."
    except Exception as e:
        return False, f"Error con hyprctl: {e}"


def send_desktop_notification(title: str, message: str) -> tuple[bool, str]:
    """Envia una notificacion al escritorio mediante notify-send."""
    logger.info("Enviando notificacion: '%s' - '%s'", title, message)
    try:
        safe_title = title.strip() or "Jota"
        safe_msg = message.strip() or "Aviso de Jota"
        subprocess.Popen(["notify-send", safe_title, safe_msg])
        return True, "Notificacion enviada."
    except Exception as e:
        return False, f"Error al enviar notificacion: {e}"


def get_pc_summary() -> tuple[bool, str]:
    """Genera un resumen hablado del estado del PC (CPU, RAM, ventana activa)."""
    # 1. Carga de CPU
    load1, _, _ = os.getloadavg()
    cores = os.cpu_count() or 1
    cpu_pct = min(100, int((load1 / cores) * 100))

    # 2. Memoria RAM
    mem_pct = 0
    try:
        total_kb, avail_kb = 0, 0
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    avail_kb = int(line.split()[1])
                if total_kb and avail_kb:
                    break
        if total_kb > 0:
            mem_pct = int(((total_kb - avail_kb) / total_kb) * 100)
    except Exception:
        pass

    # 3. Ventana activa
    active_app = ""
    try:
        res = subprocess.run(
            ["hyprctl", "activewindow", "-j"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            data: dict[str, Any] = json.loads(res.stdout)
            active_app = data.get("class", "")
    except Exception:
        pass

    msg_parts = [f"Uso de CPU al {cpu_pct}%", f"memoria al {mem_pct}%"]
    if active_app:
        msg_parts.append(f"la ventana activa es {active_app}")

    spoken = "El equipo tiene " + ", ".join(msg_parts) + "."
    return True, spoken

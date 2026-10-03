"""Temporizadores y recordatorios con aviso sonoro y notificacion simultanea."""

import asyncio
import logging
import threading
import time

from bridge.phone_manager import phone_manager
from jota.tools.system import send_desktop_notification
from jota.tts import speak

logger = logging.getLogger(__name__)


def _timer_worker(seconds: int, label: str) -> None:
    time.sleep(seconds)
    msg = f"Atencion: el temporizador para {label} ha terminado."
    logger.info("Temporizador disparado: %s", label)

    # 1. Notificacion en escritorio del PC
    send_desktop_notification("Jota - Temporizador", msg)

    # 2. Hacer sonar el telefono vinculado
    try:
        if phone_manager.is_connected():
            asyncio.run(phone_manager.ring_phone(duration_seconds=10))
    except Exception as e:
        logger.debug("No se pudo sonar el telefono para el temporizador: %s", e)

    # 3. Alerta por voz en altavoces del PC
    speak(msg)


def set_timer(seconds: int, label: str = "temporizador") -> tuple[bool, str]:
    """Inicia un temporizador en segundo plano."""
    if seconds <= 0:
        return False, "El tiempo del temporizador debe ser mayor a 0 segundos."

    clean_label = label.strip() or "temporizador"
    t = threading.Thread(target=_timer_worker, args=(seconds, clean_label), daemon=True)
    t.start()

    if seconds >= 60:
        minutes = seconds // 60
        rem_sec = seconds % 60
        time_desc = f"{minutes} minuto{'s' if minutes > 1 else ''}"
        if rem_sec > 0:
            time_desc += f" y {rem_sec} segundos"
    else:
        time_desc = f"{seconds} segundos"

    return True, f"Temporizador iniciado para {clean_label} en {time_desc}."

"""Temporizadores y recordatorios con aviso sonoro, cancelacion y notificacion simultanea."""

import asyncio
import logging
import threading
import time

from bridge.phone_manager import phone_manager
from jota.tools.system import send_desktop_notification
from jota.tts import speak

logger = logging.getLogger(__name__)

# Control concurrente de temporizadores activos
_active_timers: list[threading.Event] = []
_timer_lock = threading.Lock()


def _timer_worker(seconds: int, label: str, stop_event: threading.Event) -> None:
    # Espera en incrementos para permitir cancelacion inmediata
    start = time.time()
    while time.time() - start < seconds:
        if stop_event.is_set():
            logger.info("Temporizador cancelado: %s", label)
            return
        time.sleep(0.2)

    with _timer_lock:
        if stop_event in _active_timers:
            _active_timers.remove(stop_event)

    msg = f"Atencion: el temporizador para {label} ha terminado."
    logger.info("Temporizador disparado: %s", label)

    # 1. Notificacion en escritorio del PC
    send_desktop_notification("Jota - Temporizador", msg)

    # 2. Hacer sonar y notificar al telefono vinculado
    try:
        if phone_manager.is_connected():
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

            coro = phone_manager.ring_phone(duration_seconds=10)
            if loop and loop.is_running():
                asyncio.create_task(coro)
            else:
                asyncio.run(coro)
    except Exception as e:
        logger.debug("No se pudo sonar el telefono para el temporizador: %s", e)

    # 3. Alerta por voz en altavoces del PC
    speak(msg)


def set_timer(seconds: int, label: str = "temporizador") -> tuple[bool, str]:
    """Inicia un temporizador en segundo plano."""
    if seconds <= 0:
        return False, "El tiempo del temporizador debe ser mayor a 0 segundos."

    clean_label = label.strip() or "temporizador"
    stop_event = threading.Event()
    with _timer_lock:
        _active_timers.append(stop_event)

    t = threading.Thread(
        target=_timer_worker, args=(seconds, clean_label, stop_event), daemon=True
    )
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


def cancel_timers() -> tuple[bool, str]:
    """Cancela todos los temporizadores activos en curso."""
    with _timer_lock:
        if not _active_timers:
            return True, "No hay ningun temporizador activo para cancelar."
        count = len(_active_timers)
        for ev in _active_timers:
            ev.set()
        _active_timers.clear()

    return True, "Temporizador cancelado." if count == 1 else f"{count} temporizadores cancelados."

"""
Hotkey: escucha la tecla Copilot con evdev (push-to-talk).

IMPORTANTE: Para leer /dev/input/* sin sudo necesitas ser miembro del grupo 'input':
    sudo usermod -aG input $USER
    (re-loguéate para que el cambio surta efecto)

Para encontrar el código de tu tecla Copilot:
    python -c "import evdev; [print(d) for d in evdev.list_devices()]"
    python -m evdev.evtest   # selecciona tu teclado e inspecciona keycodes
"""

import logging
import threading
from pathlib import Path

import evdev
from evdev import InputDevice, categorize, ecodes

from jota.config import COPILOT_KEY_CODE

logger = logging.getLogger(__name__)


def find_keyboard() -> InputDevice | None:
    """
    Encuentra el primer dispositivo de teclado disponible.
    Si hay varios, selecciona el que tiene más teclas.
    """
    keyboards = []
    for path in evdev.list_devices():
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()
            # Un teclado real tiene la tecla Enter (KEY_ENTER = 28)
            if ecodes.EV_KEY in caps and ecodes.KEY_ENTER in caps[ecodes.EV_KEY]:
                keyboards.append(dev)
        except Exception:
            continue

    if not keyboards:
        return None

    # Preferir el que tiene más keys (probablemente el teclado principal)
    return max(keyboards, key=lambda d: len(d.capabilities().get(ecodes.EV_KEY, [])))


class CopilotHotkey:
    """
    Monitorea la tecla Copilot en modo push-to-talk.

    Uso:
        hotkey = CopilotHotkey(on_press=recorder.start, on_release=handle_release)
        hotkey.start()
        ...
        hotkey.stop()
    """

    def __init__(self, on_press: callable, on_release: callable):
        self._on_press = on_press
        self._on_release = on_release
        self._thread: threading.Thread | None = None
        self._running = False
        self._dev: InputDevice | None = None

    def start(self) -> None:
        """Inicia el listener de teclas en un hilo de fondo."""
        self._dev = find_keyboard()
        if self._dev is None:
            raise RuntimeError(
                "No se encontró ningún teclado. "
                "Asegúrate de estar en el grupo 'input' o ejecutar con permisos."
            )
        logger.info("Escuchando tecla Copilot en: %s (%s)", self._dev.path, self._dev.name)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Detiene el listener."""
        self._running = False
        if self._dev:
            self._dev.close()

    def _loop(self) -> None:
        """Bucle principal que lee eventos del teclado."""
        try:
            for event in self._dev.read_loop():
                if not self._running:
                    break
                if event.type != ecodes.EV_KEY:
                    continue

                key_event = categorize(event)
                if key_event.scancode != COPILOT_KEY_CODE:
                    continue

                if key_event.keystate == key_event.key_down:
                    logger.debug("Copilot key: PULSADA")
                    self._on_press()
                elif key_event.keystate == key_event.key_up:
                    logger.debug("Copilot key: SOLTADA")
                    self._on_release()

        except OSError as e:
            if self._running:
                logger.error("Error leyendo teclado: %s", e)

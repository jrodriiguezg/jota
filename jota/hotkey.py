"""
Hotkey: escucha la tecla Copilot con evdev (push-to-talk).

Monitorea todos los dispositivos de teclado conectados simultaneamente.
"""

import logging
import selectors
import threading
from collections.abc import Callable

import evdev
from evdev import InputDevice, categorize, ecodes

from jota.config import COPILOT_KEY_CODE, COPILOT_KEY_CODES

logger = logging.getLogger(__name__)


def find_keyboards() -> list[InputDevice]:
    """Encuentra todos los dispositivos que emiten eventos de teclado."""
    keyboards = []
    for path in evdev.list_devices():
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps:
                keyboards.append(dev)
        except Exception:
            continue
    return keyboards


class CopilotHotkey:
    """
    Monitorea la tecla Copilot en modo push-to-talk a traves de todos
    los dispositivos de teclado disponibles concurrentemente.
    """

    def __init__(self, on_press: Callable[[], None], on_release: Callable[[], None]):
        self._on_press = on_press
        self._on_release = on_release
        self._thread: threading.Thread | None = None
        self._running = False
        self._devices: list[InputDevice] = []
        self._selector: selectors.DefaultSelector | None = None
        self._is_pressed = False
        self._state_lock = threading.Lock()

    def start(self) -> None:
        """Inicia el listener de teclas en un hilo de fondo."""
        self._devices = find_keyboards()
        if not self._devices:
            raise RuntimeError(
                "No se encontro ningun dispositivo de entrada accesible.\n"
                "Asegurate de pertenecer al grupo 'input' (usa 'newgrp input' o re-inicia sesion)."
            )

        self._selector = selectors.DefaultSelector()
        for dev in self._devices:
            try:
                self._selector.register(dev, selectors.EVENT_READ)
                logger.info("Monitoreando teclado: %s (%s)", dev.name, dev.path)
            except Exception as e:
                logger.warning("No se pudo registrar %s: %s", dev.path, e)

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Detiene el listener y libera los descriptores de eventos."""
        self._running = False
        if self._selector:
            try:
                self._selector.close()
            except Exception:
                pass
        for dev in self._devices:
            try:
                dev.close()
            except Exception:
                pass

    def _loop(self) -> None:
        """Bucle principal que lee eventos de todos los teclados registrados."""
        while self._running and self._selector:
            try:
                events = self._selector.select(timeout=0.5)
                for key, mask in events:
                    device: InputDevice = key.fileobj
                    for event in device.read():
                        if event.type != ecodes.EV_KEY:
                            continue

                        key_event = categorize(event)
                        is_copilot = (
                            key_event.scancode == COPILOT_KEY_CODE
                            or key_event.scancode in COPILOT_KEY_CODES
                            or key_event.keycode == "KEY_F23"
                            or key_event.keycode == "KEY_COPILOT"
                            or (
                                isinstance(key_event.keycode, list)
                                and any(k in ["KEY_F23", "KEY_COPILOT"] for k in key_event.keycode)
                            )
                        )
                        if not is_copilot:
                            continue

                        # Manejar estados evitando rebotes o repeticion de tecla
                        with self._state_lock:
                            if key_event.keystate == key_event.key_down:
                                if not self._is_pressed:
                                    self._is_pressed = True
                                    logger.debug("Copilot key: PULSADA en %s", device.name)
                                    self._on_press()
                            elif key_event.keystate == key_event.key_up:
                                if self._is_pressed:
                                    self._is_pressed = False
                                    logger.debug("Copilot key: SOLTADA en %s", device.name)
                                    self._on_release()

            except (OSError, ValueError) as e:
                if self._running:
                    logger.debug("Aviso leyendo evento de entrada: %s", e)
            except Exception as e:
                if self._running:
                    logger.error("Error en bucle de hotkey: %s", e)

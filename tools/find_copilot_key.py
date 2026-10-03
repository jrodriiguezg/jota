#!/usr/bin/env python3
"""
Herramienta de diagnostico para encontrar el keycode de la tecla Copilot.
Escucha en TODOS los teclados y dispositivos de entrada conectados a la vez.

Uso:
    python tools/find_copilot_key.py

Si no muestra dispositivos en tu terminal actual:
    newgrp input
    python tools/find_copilot_key.py
"""

import selectors
import sys

import evdev
from evdev import InputDevice, categorize, ecodes


def main():
    devices_paths = evdev.list_devices()

    if not devices_paths:
        print("[!] No se encontraron dispositivos de entrada accesibles.")
        print("    Tu usuario necesita permisos del grupo 'input'.")
        print("\n    Solucion rapida para tu terminal actual:")
        print("      newgrp input")
        print("      python tools/find_copilot_key.py")
        print("\n    O ejecutalo con sudo temporalmente:")
        print("      sudo .venv/bin/python tools/find_copilot_key.py")
        sys.exit(1)

    selector = selectors.DefaultSelector()
    monitored = []

    for path in devices_paths:
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps:
                monitored.append(dev)
                selector.register(dev, selectors.EVENT_READ)
        except Exception:
            continue

    if not monitored:
        print("[!] No se encontraron dispositivos con eventos de teclas (EV_KEY).")
        sys.exit(1)

    print("====================================================")
    print(f"  Monitorizando {len(monitored)} dispositivos con teclas:")
    for d in monitored:
        print(f"   * {d.name} ({d.path})")
    print("====================================================")
    print("\nPulsa la tecla Copilot (o cualquier tecla) para ver su codigo.")
    print("Ctrl+C para salir.\n")

    try:
        while True:
            for key, mask in selector.select():
                device = key.fileobj
                for event in device.read():
                    if event.type == ecodes.EV_KEY:
                        key_event = categorize(event)
                        state = "PULSADA" if key_event.keystate == key_event.key_down else (
                            "SOLTADA" if key_event.keystate == key_event.key_up else "REPETIDA"
                        )
                        scancode_hex = f"{key_event.scancode:#06x}"
                        print(
                            f"[{device.name}] "
                            f"scancode: {scancode_hex} ({key_event.scancode}) | "
                            f"keycode: {key_event.keycode} ({key_event.keystate}) | "
                            f"estado: {state}"
                        )
                        if "COPILOT" in str(key_event.keycode) or "F23" in str(key_event.keycode):
                            print(f"  --> Posible tecla Copilot detectada: {scancode_hex}")
    except KeyboardInterrupt:
        print("\nFinalizado.")


if __name__ == "__main__":
    main()

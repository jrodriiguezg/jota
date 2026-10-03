#!/usr/bin/env python3
"""
Herramienta de diagnóstico para encontrar el keycode de la tecla Copilot.
Ejecuta: python tools/find_copilot_key.py
Pulsa la tecla Copilot y mira el keycode que aparece.
"""

import evdev
from evdev import InputDevice, categorize, ecodes


def main():
    devices = [InputDevice(path) for path in evdev.list_devices()]

    print("Dispositivos disponibles:")
    for i, dev in enumerate(devices):
        print(f"  [{i}] {dev.path} — {dev.name}")

    choice = input("\nElige el número de tu teclado: ").strip()
    dev = devices[int(choice)]

    print(f"\nEscuchando eventos en: {dev.name}")
    print("Pulsa la tecla Copilot (Ctrl+C para salir)...\n")

    for event in dev.read_loop():
        if event.type == ecodes.EV_KEY:
            key = categorize(event)
            if key.keystate in (key.key_down, key.key_up):
                state = "PULSADA" if key.keystate == key.key_down else "SOLTADA"
                print(f"  scancode: {key.scancode:#06x} ({key.scancode})  keycode: {key.keycode}  [{state}]")


if __name__ == "__main__":
    main()

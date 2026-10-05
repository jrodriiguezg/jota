"""
Generador de emparejamiento por codigo QR para Jota Link.
Permite vincular la app Android escaneando la pantalla o terminal en un solo paso.
"""

import io
import json
import logging
import socket
from typing import Any

from bridge.config import BRIDGE_API_KEY, BRIDGE_PORT
from bridge.pc_ops import get_pc_network_info

logger = logging.getLogger(__name__)


def get_local_ip() -> str:
    """Detecta la IP local de la maquina en la red de area local."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No necesita conectar realmente, solo selecciona la interfaz saliente
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def get_pairing_payload() -> dict[str, Any]:
    """Genera el diccionario de datos de emparejamiento para el cliente."""
    net_info = get_pc_network_info()
    local_ip = get_local_ip()
    url = f"http://{local_ip}:{BRIDGE_PORT}"

    return {
        "url": url,
        "api_key": BRIDGE_API_KEY,
        "mac": net_info.get("primary_mac", ""),
        "hostname": net_info.get("hostname", "jota-pc"),
    }


def generate_pairing_qr_ascii() -> str:
    """Genera un codigo QR en formato texto/ANSI para visualizarlo en la consola."""
    try:
        import qrcode

        payload_str = json.dumps(get_pairing_payload())
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=2,
        )
        qr.add_data(payload_str)
        qr.make(fit=True)

        output = io.StringIO()
        qr.print_ascii(out=output, invert=True)
        return output.getvalue()
    except Exception as e:
        logger.error("Error generando QR: %s", e)
        return json.dumps(get_pairing_payload(), indent=2)


if __name__ == "__main__":
    payload = get_pairing_payload()
    print("==================================================")
    print("  Emparejamiento Rapido Jota Link (Android <-> PC)")
    print("==================================================")
    print(f"URL: {payload['url']}")
    print(f"Host: {payload['hostname']}")
    print(f"MAC: {payload['mac']}")
    print("==================================================")
    print("Escanea este codigo con la aplicacion:")
    print()
    print(generate_pairing_qr_ascii())
    print("O copia este JSON en los ajustes de la app:")
    print(json.dumps(payload))
    print("==================================================")

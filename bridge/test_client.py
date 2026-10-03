"""
Cliente de prueba y simulador de dispositivo Android para Jota Bridge.
Permite interactuar con Jota desde la terminal a traves de la red Tailscale:
- Mantiene el canal WebSocket simulando un movil (reporte de bateria, receptor de ring/clipboard).
- Consulta estado del PC, captura de pantalla, portapapeles y descarga de archivos.
- Envia prompts de texto o archivos de audio.

Uso:
    python bridge/test_client.py --help
"""

import argparse
import asyncio
import json
from pathlib import Path

import httpx

try:
    import websockets
except ImportError:
    websockets = None


async def run_phone_listener(base_url: str, api_key: str, device_id: str, battery: int):
    """Simula el servicio receptor en segundo plano del telefono."""
    if websockets is None:
        print("El paquete 'websockets' no esta instalado para la simulacion WS.")
        return

    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    url = f"{ws_url}/ws/phone?token={api_key}&device_id={device_id}&model=Simulated_Android"
    print(f"Conectando WebSocket simulado a: {url}")

    while True:
        try:
            async with websockets.connect(url) as ws:
                print(f"[Phone] Conectado exitosamente al Bridge como '{device_id}'")
                # Reportar estado inicial de bateria
                await ws.send(
                    json.dumps(
                        {
                            "event": "status_update",
                            "payload": {
                                "battery": battery,
                                "is_charging": False,
                                "model": "Pixel 8 Pro (Simulado)",
                            },
                        }
                    )
                )

                while True:
                    raw_msg = await ws.recv()
                    data = json.loads(raw_msg)
                    event = data.get("event")
                    payload = data.get("payload", {})
                    print(f"\n[Phone RECIBIDO] Evento: '{event}' | Datos: {payload}")

                    if event == "ring":
                        duration = payload.get("duration_seconds", 10)
                        print(f"ALERTA: Sonando alarma al 100% de volumen durante {duration}s!")
                    elif event == "clipboard":
                        text = payload.get("text", "")
                        print(f"PORTAPAPELES ANDROID: Copiado al portapapeles: {text!r}")
                    elif event == "open_url":
                        url_to_open = payload.get("url", "")
                        print(f"NAVEGADOR ANDROID: Abriendo enlace: {url_to_open}")

        except Exception as e:
            print(f"[Phone] Desconexion o error: {e}. Reintentando en 3s...")
            await asyncio.sleep(3)


def ask_pc(base_url: str, api_key: str, prompt: str):
    """Envia una pregunta por texto a Jota en el PC."""
    headers = {"X-Bridge-Key": api_key}
    with httpx.Client(base_url=base_url, headers=headers, timeout=30.0) as client:
        resp = client.post("/api/v1/text/ask", json={"prompt": prompt, "generate_audio": False})
        if resp.status_code == 200:
            data = resp.json()
            print("\nRespuesta de Jota:")
            print(f"Texto: {data.get('response_text')}")
            if data.get("tool_executed"):
                print(f"Herramienta ejecutada: {data['tool_executed']}")
        else:
            print(f"Error {resp.status_code}: {resp.text}")


def get_status(base_url: str, api_key: str):
    """Consulta el estado del PC."""
    headers = {"X-Bridge-Key": api_key}
    with httpx.Client(base_url=base_url, headers=headers, timeout=5.0) as client:
        resp = client.get("/api/v1/pc/status")
        if resp.status_code == 200:
            print(json.dumps(resp.json(), indent=2))
        else:
            print(f"Error {resp.status_code}: {resp.text}")


def get_screenshot(base_url: str, api_key: str, out_path: str = "pc_screenshot.png"):
    """Descarga una captura de pantalla del PC."""
    headers = {"X-Bridge-Key": api_key}
    with httpx.Client(base_url=base_url, headers=headers, timeout=10.0) as client:
        resp = client.get("/api/v1/pc/screenshot")
        if resp.status_code == 200:
            Path(out_path).write_bytes(resp.content)
            print(f"Captura guardada en: {out_path} ({len(resp.content)} bytes)")
        else:
            print(f"Error {resp.status_code}: {resp.text}")


def download_file(base_url: str, api_key: str, remote_path: str, local_out: str):
    """Descarga un archivo del PC."""
    headers = {"X-Bridge-Key": api_key}
    with httpx.Client(base_url=base_url, headers=headers, timeout=30.0) as client:
        resp = client.get("/api/v1/pc/file", params={"path": remote_path})
        if resp.status_code == 200:
            Path(local_out).write_bytes(resp.content)
            print(f"Archivo descargado en: {local_out} ({len(resp.content)} bytes)")
        else:
            print(f"Error {resp.status_code}: {resp.text}")


def main():
    parser = argparse.ArgumentParser(description="Cliente de prueba para Jota Bridge")
    parser.add_argument("--url", default="http://127.0.0.1:8765", help="URL base del bridge")
    parser.add_argument("--key", default="jota-secret-tailscale-key", help="Clave API del bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcomando: simulate-phone
    sim_p = subparsers.add_parser(
        "simulate-phone", help="Simula un dispositivo Android conectado por WS"
    )
    sim_p.add_argument("--device-id", default="android_pixel8", help="ID del dispositivo")
    sim_p.add_argument("--battery", type=int, default=85, help="Porcentaje de bateria simulado")

    # Subcomando: ask
    ask_p = subparsers.add_parser("ask", help="Envia una pregunta de texto al PC")
    ask_p.add_argument("prompt", help="Texto de la consulta")

    # Subcomando: status
    subparsers.add_parser("status", help="Obtiene estado del PC")

    # Subcomando: screenshot
    ss_p = subparsers.add_parser("screenshot", help="Obtiene captura de pantalla del PC")
    ss_p.add_argument("--out", default="screenshot_pc.png", help="Archivo de destino")

    # Subcomando: file
    file_p = subparsers.add_parser("file", help="Descarga un archivo del PC")
    file_p.add_argument("path", help="Ruta en el PC")
    file_p.add_argument("--out", required=True, help="Ruta local de guardado")

    args = parser.parse_args()

    if args.command == "simulate-phone":
        asyncio.run(run_phone_listener(args.url, args.key, args.device_id, args.battery))
    elif args.command == "ask":
        ask_pc(args.url, args.key, args.prompt)
    elif args.command == "status":
        get_status(args.url, args.key)
    elif args.command == "screenshot":
        get_screenshot(args.url, args.key, args.out)
    elif args.command == "file":
        download_file(args.url, args.key, args.path, args.out)


if __name__ == "__main__":
    main()

"""
Modulo de descubrimiento y canales de proximidad para Jota Bridge.
Gestiona:
1. Descubrimiento automatico ZeroConf / mDNS (_jota-bridge._tcp.local.)
2. Configuracion de tunel USB por cable mediante ADB Reverse (tcp:PORT -> tcp:PORT)
3. Deteccion de interfaces de red cercanas (USB Tethering, Bluetooth PAN, Wi-Fi local)
"""

import logging
import os
import shutil
import socket
import subprocess
from typing import Any

logger = logging.getLogger("jota.bridge.discovery")


def get_local_ip() -> str:
    """Obtiene la IP local primaria del host en la red LAN o interfaz activa."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # No realiza conexion real pero permite al kernel determinar la interfaz de salida
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


async def register_mdns_service(port: int = 8765) -> tuple[Any, Any] | None:
    """
    Registra el servicio mDNS/ZeroConf para descubrimiento automatico desde Android.
    Tipo: _jota-bridge._tcp.local.
    Devuelve la tupla (zeroconf_instance, service_info) o None si falla.
    """
    try:
        from zeroconf import IPVersion, ServiceInfo
        from zeroconf.asyncio import AsyncZeroconf
    except ImportError:
        logger.info("zeroconf no esta instalado. Descubrimiento mDNS desactivado.")
        return None

    try:
        local_ip = get_local_ip()
        hostname = socket.gethostname()
        service_type = "_jota-bridge._tcp.local."
        service_name = f"Jota-Bridge-{hostname}.{service_type}"

        info = ServiceInfo(
            service_type,
            service_name,
            addresses=[socket.inet_aton(local_ip)],
            port=port,
            properties={
                "version": "0.2.0",
                "auth": "required",
                "host": hostname,
                "api": "/api/v1",
            },
            server=f"{hostname}.local.",
        )

        azc = AsyncZeroconf(ip_version=IPVersion.V4Only)
        await azc.async_register_service(info, allow_name_change=True)
        logger.info("Servicio mDNS anunciado: %s en %s:%d", info.name, local_ip, port)
        return (azc, info)
    except Exception as e:
        logger.warning("Fallo al registrar anuncio mDNS/ZeroConf: %s", repr(e))
        return None


async def unregister_mdns_service(service_handle: tuple[Any, Any] | None) -> None:
    """Desregistra y limpia el servicio mDNS de forma asincrona."""
    if not service_handle:
        return
    try:
        azc, info = service_handle
        await azc.async_unregister_service(info)
        await azc.async_close()
        logger.info("Servicio mDNS desregistrado correctamente.")
    except Exception as e:
        logger.debug("Error cerrando mDNS: %s", e)


def setup_adb_reverse(port: int = 8765) -> tuple[bool, str]:
    """
    Configura reenvio de puertos inverso por cable USB usando ADB (Android Debug Bridge).
    Permite que la app Android en el telefono conectado por USB acceda al servidor
    en http://127.0.0.1:{port} sin requerir WiFi ni datos moviles.
    """
    adb_bin = shutil.which("adb")
    if not adb_bin:
        return False, "ADB no esta instalado en el sistema."

    try:
        # Verificar si hay dispositivos conectados
        res_devices = subprocess.run(
            [adb_bin, "devices"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        lines = [line.strip() for line in res_devices.stdout.splitlines() if line.strip()]
        # Formato habitual: "List of devices attached", luego "<serial>\tdevice"
        attached = [dev_line for dev_line in lines[1:] if "\tdevice" in dev_line]

        if not attached:
            return False, "No se detecto dispositivo Android conectado por USB con depuracion."

        device_serial = attached[0].split("\t")[0]
        # Configurar adb reverse
        res_reverse = subprocess.run(
            [adb_bin, "-s", device_serial, "reverse", f"tcp:{port}", f"tcp:{port}"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if res_reverse.returncode == 0:
            msg = f"Canal USB ADB activo ({device_serial}): el movil puede conectarse a http://127.0.0.1:{port}"
            logger.info(msg)
            return True, msg
        else:
            err = res_reverse.stderr.strip() or "Error al ejecutar adb reverse"
            return False, err
    except Exception as e:
        return False, f"Excepcion configurando ADB reverse: {e}"


def get_nearby_channels_status(port: int = 8765) -> dict[str, Any]:
    """
    Detecta los canales de comunicacion disponibles entre el PC y dispositivos cercanos:
    - Wi-Fi / LAN local
    - Cable USB (ADB Reverse y USB Tethering)
    - Bluetooth (PAN / BNEP)
    """
    channels = {
        "wifi_lan": {"active": False, "ip": None, "port": port},
        "usb_cable": {"adb_available": False, "devices": [], "tethering_interface": None},
        "bluetooth": {"pan_active": False, "interface": None, "adapter_present": False},
    }

    # 1. IP local LAN
    local_ip = get_local_ip()
    if local_ip != "127.0.0.1":
        channels["wifi_lan"]["active"] = True
        channels["wifi_lan"]["ip"] = local_ip

    # 2. Interfaces de red activas en Linux
    net_path = "/sys/class/net"
    if os.path.exists(net_path):
        try:
            for iface in os.listdir(net_path):
                # Detectar Bluetooth PAN (bnep0, bnep1...)
                if iface.startswith("bnep"):
                    channels["bluetooth"]["pan_active"] = True
                    channels["bluetooth"]["interface"] = iface
                # Detectar USB Tethering (usb0, rndis0, o enp*u* interfaz ethernet usb)
                elif (
                    iface.startswith(("usb", "rndis"))
                    or ("u" in iface and iface.startswith("enp"))
                ):
                    # Verificar si la interfaz tiene carrier/estado UP
                    operstate_file = os.path.join(net_path, iface, "operstate")
                    if os.path.exists(operstate_file):
                        with open(operstate_file) as f:
                            state = f.read().strip()
                        if state in ("up", "unknown"):
                            channels["usb_cable"]["tethering_interface"] = iface
        except Exception:
            pass

    # 3. Adaptador Bluetooth general en el host
    bluetooth_path = "/sys/class/bluetooth"
    if os.path.exists(bluetooth_path) and os.listdir(bluetooth_path):
        channels["bluetooth"]["adapter_present"] = True

    # 4. Deteccion de dispositivos ADB por cable USB
    adb_bin = shutil.which("adb")
    if adb_bin:
        channels["usb_cable"]["adb_available"] = True
        try:
            res = subprocess.run(
                [adb_bin, "devices"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            for dev_line in lines[1:]:
                if "\t" in dev_line:
                    serial, dev_state = dev_line.split("\t", 1)
                    channels["usb_cable"]["devices"].append({"serial": serial, "state": dev_state})
        except Exception:
            pass

    return channels

"""
Control de conectividad Bluetooth para Jota mediante bluetoothctl.
Permite conectar, desconectar, consultar estado y encender/apagar el controlador.
"""

import logging
import re
import shutil
import subprocess

logger = logging.getLogger(__name__)


def _run_bluetoothctl(args: list[str], timeout: float = 5.0) -> tuple[int, str]:
    """Ejecuta una orden con el binario bluetoothctl de forma segura."""
    bin_path = shutil.which("bluetoothctl")
    if not bin_path:
        return -1, "bluetoothctl no esta instalado en el sistema."

    try:
        proc = subprocess.run(
            [bin_path] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip()
    except subprocess.TimeoutExpired:
        return -1, "Tiempo de espera agotado al consultar Bluetooth."
    except Exception as e:
        logger.error("Error ejecutando bluetoothctl %s: %s", args, e)
        return -1, str(e)


def _get_devices(device_type: str = "devices") -> list[dict[str, str]]:
    """Obtiene lista de dispositivos conocidos (Paired, Connected, o todos)."""
    args = [device_type] if device_type != "all" else ["devices"]
    code, output = _run_bluetoothctl(args)
    if code != 0 or not output:
        return []

    devices = []
    # Formato tipico de linea: Device DC:2C:26:XX:XX:XX Nombre del Dispositivo
    for line in output.splitlines():
        line = line.strip()
        match = re.match(r"Device\s+([0-9A-Fa-f:]{17})\s+(.+)$", line)
        if match:
            mac, name = match.group(1), match.group(2).strip()
            devices.append({"mac": mac, "name": name})
    return devices


def bluetooth_control(action: str = "status", device: str = "") -> tuple[bool, str]:
    """
    Gestiona el subsistema Bluetooth del equipo.
    Acciones: status, on/encender, off/apagar, connect/conectar, disconnect/desconectar.
    """
    clean_action = str(action).strip().lower()
    clean_device = str(device).strip().lower()

    if not shutil.which("bluetoothctl"):
        return False, "La herramienta bluetoothctl no esta disponible en el equipo."

    # 1. Estado general
    if clean_action in ("status", "estado", "info", "get"):
        code, show_out = _run_bluetoothctl(["show"])
        if "Powered: yes" not in show_out:
            return True, "El Bluetooth del equipo esta apagado."

        connected = _get_devices("devices Connected")
        if not connected:
            paired = _get_devices("devices Paired")
            paired_count = len(paired)
            if paired_count > 0:
                return (
                    True,
                    f"Bluetooth encendido. Hay {paired_count} dispositivos emparejados, "
                    "pero ninguno conectado actualmente.",
                )
            return True, "Bluetooth encendido. No hay dispositivos conectados."

        names = ", ".join(d["name"] for d in connected)
        return True, f"Bluetooth conectado a: {names}."

    # 2. Encendido
    if clean_action in ("on", "encender", "power_on", "activar"):
        code, _ = _run_bluetoothctl(["power", "on"])
        if code == 0:
            return True, "Bluetooth encendido."
        return False, "No se pudo encender el Bluetooth."

    # 3. Apagado
    if clean_action in ("off", "apagar", "power_off", "desactivar"):
        code, _ = _run_bluetoothctl(["power", "off"])
        if code == 0:
            return True, "Bluetooth apagado."
        return False, "No se pudo apagar el Bluetooth."

    # 4. Conectar a un dispositivo
    if clean_action in ("connect", "conectar", "enlazar"):
        paired = _get_devices("devices Paired")
        if not paired:
            paired = _get_devices("devices")

        if not paired:
            return False, "No hay ningun dispositivo Bluetooth registrado en el equipo."

        target = None
        if clean_device:
            for d in paired:
                if clean_device in d["name"].lower() or clean_device in d["mac"].lower():
                    target = d
                    break
        else:
            # Si no se especifica dispositivo, conectar al primer dispositivo emparejado
            target = paired[0]

        if not target:
            return (
                False,
                f"No encontre ningun dispositivo Bluetooth que coincida con '{device}'.",
            )

        code, out = _run_bluetoothctl(["connect", target["mac"]], timeout=8.0)
        if "Connection successful" in out or code == 0:
            return True, f"Conectado a {target['name']}."
        return False, f"No se pudo conectar a {target['name']}."

    # 5. Desconectar dispositivo
    if clean_action in ("disconnect", "desconectar", "separar"):
        connected = _get_devices("devices Connected")
        if not connected:
            return True, "No habia ningun dispositivo Bluetooth conectado."

        target = None
        if clean_device:
            for d in connected:
                if clean_device in d["name"].lower() or clean_device in d["mac"].lower():
                    target = d
                    break
        else:
            target = connected[0]

        if not target:
            return (
                False,
                f"El dispositivo '{device}' no figura como conectado en el sistema.",
            )

        code, out = _run_bluetoothctl(["disconnect", target["mac"]], timeout=6.0)
        if "Successful disconnected" in out or code == 0:
            return True, f"Desconectado de {target['name']}."
        return False, f"Fallo al desconectar {target['name']}."

    return False, f"Accion Bluetooth '{action}' no soportada."

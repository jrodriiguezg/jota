"""
Modulo de identidad de hardware para Jota.
Genera un identificador de nodo inmutable, determinista e infalsificable (node_id)
basado en caracteristicas fisicas de la maquina host:
- /etc/machine-id (o /var/lib/dbus/machine-id)
- DMI product UUID o huella de hardware del sistema
- Direccion MAC fisica primaria (descartando interfaces virtuales y VPN)
"""

import hashlib
import os
import platform
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

DEFAULT_CLUSTER_SALT = "jota-cluster-salt-v1"


def get_machine_id() -> str:
    """
    Obtiene el identificador unico del sistema operativo.
    Lee /etc/machine-id o /var/lib/dbus/machine-id.
    """
    candidates = [
        Path("/etc/machine-id"),
        Path("/var/lib/dbus/machine-id"),
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                content = candidate.read_text(encoding="utf-8").strip()
                if content and len(content) >= 16:
                    return content
        except (PermissionError, OSError):
            continue

    # Fallback para entornos donde no exista machine-id (ej. contenedores minimos)
    try:
        boot_id_path = Path("/proc/sys/kernel/random/boot_id")
        if boot_id_path.is_file():
            boot_id = boot_id_path.read_text(encoding="utf-8").strip()
            if boot_id:
                return f"boot_{boot_id}"
    except (PermissionError, OSError):
        pass

    # Ultimo fallback determinista: hash de hostname y plataforma
    fallback_seed = f"{socket.gethostname()}:{platform.node()}:{platform.system()}"
    return hashlib.sha256(fallback_seed.encode("utf-8")).hexdigest()


def get_dmi_hardware_id() -> str:
    """
    Obtiene el UUID de DMI o una huella compuesta de hardware DMI.
    Maneja permisos no privilegiados con degradacion elegante.
    """
    dmi_dir = Path("/sys/class/dmi/id")
    if not dmi_dir.is_dir():
        dmi_dir = Path("/sys/devices/virtual/dmi/id")

    # 1. Intentar leer product_uuid directamente (requiere root en la mayoria de distribuciones)
    uuid_file = dmi_dir / "product_uuid"
    try:
        if uuid_file.is_file():
            val = uuid_file.read_text(encoding="utf-8").strip()
            if val and val.lower() not in ("none", "not specified", "to be filled by o.e.m."):
                return val
    except (PermissionError, OSError):
        pass

    # 2. Leer campos publicos accesibles sin privilegios de root
    public_fields = [
        "product_name",
        "board_name",
        "sys_vendor",
        "product_family",
        "board_vendor",
    ]
    collected = []
    if dmi_dir.is_dir():
        for field in public_fields:
            field_path = dmi_dir / field
            try:
                if field_path.is_file():
                    val = field_path.read_text(encoding="utf-8").strip()
                    if val:
                        collected.append(f"{field}={val}")
            except (PermissionError, OSError):
                continue

    if collected:
        return ";".join(collected)

    # 3. Fallback: extraer modelo del procesador de /proc/cpuinfo
    try:
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.is_file():
            for line in cpuinfo.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "model name" in line:
                    return line.strip()
    except (PermissionError, OSError):
        pass

    return f"generic_arch_{platform.machine()}"


def get_primary_mac_address() -> str:
    """
    Obtiene la direccion MAC fisica de la interfaz de red principal.
    Descarta interfaces virtuales como loopback, docker, tailscale, veth y bridges.
    """
    net_dir = Path("/sys/class/net")
    ignored_prefixes = (
        "lo",
        "docker",
        "tailscale",
        "veth",
        "br-",
        "tun",
        "tap",
        "virbr",
        "dummy",
    )

    if net_dir.is_dir():
        try:
            interfaces = sorted(os.listdir(net_dir))
            # Priorizar interfaces cableadas (eth, enp, eno) y luego wifi (wlan, wlp)
            priority_order = []
            for iface in interfaces:
                if any(iface.startswith(prefix) for prefix in ignored_prefixes):
                    continue
                priority_order.append(iface)

            for iface in priority_order:
                addr_path = net_dir / iface / "address"
                try:
                    if addr_path.is_file():
                        mac = addr_path.read_text(encoding="utf-8").strip().lower()
                        # Validar que no sea una MAC nula
                        if mac and mac != "00:00:00:00:00:00" and len(mac) == 17:
                            return mac
                except (PermissionError, OSError):
                    continue
        except OSError:
            pass

    # Fallback mediante uuid.getnode()
    node = uuid.getnode()
    # Si el bit multicast esta activo (bit 40), se genero de forma pseudo-aleatoria
    mac_bytes = (
        (node >> 40) & 0xFF,
        (node >> 32) & 0xFF,
        (node >> 24) & 0xFF,
        (node >> 16) & 0xFF,
        (node >> 8) & 0xFF,
        node & 0xFF,
    )
    return ":".join(f"{b:02x}" for b in mac_bytes)


def calculate_hardware_fingerprint(salt: str = DEFAULT_CLUSTER_SALT) -> str:
    """
    Calcula el hash criptografico SHA-256 compuesto de las tres fuentes de entropia.
    """
    m_id = get_machine_id()
    d_id = get_dmi_hardware_id()
    mac = get_primary_mac_address()

    composite = f"{m_id}:{d_id}:{mac}:{salt}"
    return hashlib.sha256(composite.encode("utf-8")).hexdigest()


def get_node_id(salt: str = DEFAULT_CLUSTER_SALT) -> str:
    """
    Devuelve el identificador unico de nodo (ej: 'node_a1b2c3d4e5f67890').
    Si existe un archivo local persistido en ~/.config/jota/node_id, lo respeta.
    """
    # 1. Comprobar si existe archivo persistido
    config_dir = Path.home() / ".config" / "jota"
    node_id_file = config_dir / "node_id"
    try:
        if node_id_file.is_file():
            cached_id = node_id_file.read_text(encoding="utf-8").strip()
            if cached_id and cached_id.startswith("node_") and len(cached_id) == 21:
                return cached_id
    except (PermissionError, OSError):
        pass

    # 2. Generar huella a partir de hardware
    fingerprint = calculate_hardware_fingerprint(salt=salt)
    node_id = f"node_{fingerprint[:16]}"

    # 3. Intentar persistir para acelerar lecturas posteriores
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        node_id_file.write_text(node_id + "\n", encoding="utf-8")
        node_id_file.chmod(0o600)
    except (PermissionError, OSError):
        pass

    return node_id


def is_tailscale_interface_present() -> bool:
    """Comprueba si existe la interfaz tailscale0 en el sistema."""
    return Path("/sys/class/net/tailscale0").exists()


def get_tailscale_ip() -> str:
    """Obtiene la IP asignada por Tailscale si esta activa."""
    try:
        res = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            ip = res.stdout.strip()
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass
    return ""


def get_node_metadata() -> dict[str, Any]:
    """
    Recopila metadatos del nodo actual para registro y diagnostico en el Hub.
    """
    ts_ip = get_tailscale_ip()
    return {
        "node_id": get_node_id(),
        "hostname": socket.gethostname(),
        "os": platform.system(),
        "release": platform.release(),
        "arch": platform.machine(),
        "python_version": platform.python_version(),
        "has_tailscale": is_tailscale_interface_present() or bool(ts_ip),
        "tailscale_ip": ts_ip,
        "mac_primary": get_primary_mac_address(),
    }

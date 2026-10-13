"""
Cliente y demonio de satelite para el ecosistema Jota.
Gestiona el ciclo de vida del nodo (interactivo Desktop o headless de solo lectura),
auto-registro criptografico con el Hub, latidos periodicos y reporte de telemetria.
"""

import argparse
import asyncio
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from jota.identity import (
    calculate_hardware_fingerprint,
    get_node_id,
    get_node_metadata,
)

logger = logging.getLogger("jota.satellite")

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "jota" / "satelite.yaml"


@dataclass
class SatelliteConfig:
    """Configuracion declarativa del satelite Jota."""

    node_name: str = ""
    mode: str = "desktop"  # 'desktop' o 'headless'
    hub_url: str = "http://127.0.0.1:8765"
    hub_token: str = ""
    port: int = 8765
    heartbeat_interval_sec: float = 15.0
    telemetry_interval_sec: float = 30.0
    is_gpu_worker: bool = False
    gpu_info: str = ""
    services: list[str] = field(default_factory=lambda: ["sshd", "docker", "podman"])

    def __post_init__(self):
        if not self.node_name:
            self.node_name = socket.gethostname() or "jota-satellite"
        if not self.hub_token:
            self.hub_token = os.getenv("JOTA_BRIDGE_KEY", os.getenv("JOTA_HUB_TOKEN", ""))
        if not self.gpu_info:
            has_gpu, info = detect_local_gpu()
            if has_gpu:
                self.is_gpu_worker = True
                self.gpu_info = info

    @classmethod
    def load_from_file(cls, path: Path | str = DEFAULT_CONFIG_PATH) -> "SatelliteConfig":
        """Carga la configuracion desde archivo YAML o JSON."""
        file_path = Path(path)
        if not file_path.is_file():
            return cls.from_env()

        try:
            import yaml

            data = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            logger.warning("No se pudo parsear %s (%s). Usando variables de entorno.", path, e)
            return cls.from_env()

        node_cfg = data.get("node", {})
        hub_cfg = data.get("hub", {})
        telemetry_cfg = data.get("telemetry", {})

        return cls(
            node_name=node_cfg.get("name", socket.gethostname()),
            mode=node_cfg.get("mode", "desktop"),
            hub_url=f"http://{hub_cfg.get('host', '127.0.0.1')}:{hub_cfg.get('port', 8765)}",
            hub_token=hub_cfg.get("token", ""),
            port=int(hub_cfg.get("port", 8765)),
            heartbeat_interval_sec=float(hub_cfg.get("heartbeat_interval_sec", 15.0)),
            telemetry_interval_sec=float(telemetry_cfg.get("interval_sec", 30.0)),
            services=telemetry_cfg.get("systemd_services", ["sshd", "docker", "podman"]),
        )

    @classmethod
    def from_env(cls) -> "SatelliteConfig":
        """Genera configuracion a partir de variables de entorno del sistema."""
        hub_host = os.getenv("JOTA_HUB_HOST", "127.0.0.1")
        hub_port = int(os.getenv("JOTA_HUB_PORT", "8765"))
        hub_url = os.getenv("JOTA_HUB_URL", f"http://{hub_host}:{hub_port}")
        token = os.getenv("JOTA_BRIDGE_KEY", os.getenv("JOTA_HUB_TOKEN", ""))
        mode = os.getenv("JOTA_SATELLITE_MODE", "desktop").lower()
        name = os.getenv("JOTA_SATELLITE_NAME", socket.gethostname())

        return cls(
            node_name=name,
            mode=mode,
            hub_url=hub_url,
            hub_token=token,
            port=hub_port,
        )

    def save_to_file(self, path: Path | str = DEFAULT_CONFIG_PATH) -> None:
        """Guarda la configuracion en formato YAML con permisos 0600."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.parent.chmod(0o700)
        except OSError:
            pass

        import yaml

        content = {
            "node": {
                "name": self.node_name,
                "mode": self.mode,
            },
            "hub": {
                "host": self.hub_url.replace("http://", "").replace("https://", "").split(":")[0],
                "port": self.port,
                "token": self.hub_token,
                "heartbeat_interval_sec": self.heartbeat_interval_sec,
            },
            "telemetry": {
                "interval_sec": self.telemetry_interval_sec,
                "systemd_services": self.services,
            },
        }
        target.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
        try:
            target.chmod(0o600)
        except OSError:
            pass


def detect_local_gpu() -> tuple[bool, str]:
    """Detecta si el host cuenta con aceleracion GPU NVIDIA util para offload."""
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return False, ""

    try:
        res = subprocess.run(
            [nvidia_smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            lines = res.stdout.strip().splitlines()
            if lines:
                parts = lines[0].split(",")
                gpu_name = parts[0].strip()
                vram_mb = parts[1].strip() if len(parts) > 1 else ""
                info = f"{gpu_name} ({vram_mb} MB)" if vram_mb else gpu_name
                return True, info
    except Exception as e:
        logger.debug("Error al consultar nvidia-smi: %s", e)

    return False, ""


def collect_host_telemetry(services: list[str] = None) -> dict[str, Any]:
    """
    Recopila metricas de recursos, contenedores locales y servicios systemd
    utilizando llamadas ligeras del kernel Linux y comandos POSIX.
    """
    # 1. CPU
    cpu_percent = 0.0
    try:
        with open("/proc/loadavg") as f:
            load1 = float(f.read().split()[0])
        cores = os.cpu_count() or 1
        cpu_percent = min(100.0, round((load1 / cores) * 100.0, 1))
    except Exception:
        pass

    # 2. RAM
    ram_percent = 0.0
    ram_used_mb = 0.0
    ram_total_mb = 0.0
    try:
        total_kb = 0
        avail_kb = 0
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    avail_kb = int(line.split()[1])
                if total_kb and avail_kb:
                    break
        if total_kb > 0:
            used_kb = total_kb - avail_kb
            ram_percent = round((used_kb / total_kb) * 100.0, 1)
            ram_used_mb = round(used_kb / 1024, 1)
            ram_total_mb = round(total_kb / 1024, 1)
    except Exception:
        pass

    # 3. Disco
    disk_percent = 0.0
    disk_free_gb = 0.0
    try:
        st = os.statvfs("/")
        total_bytes = st.f_blocks * st.f_frsize
        free_bytes = st.f_bavail * st.f_frsize
        if total_bytes > 0:
            used_bytes = total_bytes - free_bytes
            disk_percent = round((used_bytes / total_bytes) * 100.0, 1)
            disk_free_gb = round(free_bytes / (1024**3), 1)
    except Exception:
        pass

    # 4. Contenedores Docker / Podman
    containers = []
    for engine in ("docker", "podman"):
        bin_path = shutil.which(engine)
        if not bin_path:
            continue
        try:
            res = subprocess.run(
                [bin_path, "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.strip().splitlines():
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        containers.append({
                            "name": parts[0].strip(),
                            "status": parts[1].strip(),
                            "image": parts[2].strip(),
                            "engine": engine,
                        })
                break  # Si el primer motor responde, usarlo
        except Exception:
            continue

    # 5. Servicios systemd
    systemd_status = []
    systemctl = shutil.which("systemctl")
    if systemctl and services:
        for s in services:
            try:
                res = subprocess.run(
                    [systemctl, "is-active", s],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                systemd_status.append(f"{s}:{res.stdout.strip() or 'inactive'}")
            except Exception:
                systemd_status.append(f"{s}:unknown")

    return {
        "cpu_percent": cpu_percent,
        "ram_percent": ram_percent,
        "ram_used_mb": ram_used_mb,
        "ram_total_mb": ram_total_mb,
        "disk_percent": disk_percent,
        "disk_free_gb": disk_free_gb,
        "containers": containers,
        "systemd_services": systemd_status,
    }


class SatelliteClient:
    """Cliente de enlace con Jota Hub."""

    def __init__(self, config: SatelliteConfig):
        self.config = config
        self.node_id = get_node_id()
        self.hardware_fingerprint = calculate_hardware_fingerprint()
        self.metadata = get_node_metadata()
        self.is_registered = False

    @property
    def auth_headers(self) -> dict[str, str]:
        return {
            "X-Jota-Token": self.config.hub_token,
            "User-Agent": f"JotaSatellite/{self.config.mode}",
        }

    async def register(self, client: httpx.AsyncClient) -> tuple[bool, str]:
        """Realiza el apreton de manos y registro inicial en el Hub."""
        url = f"{self.config.hub_url.rstrip('/')}/api/v1/nodes/register"
        payload = {
            "node_id": self.node_id,
            "name": self.config.node_name,
            "mode": self.config.mode,
            "hardware_fingerprint": self.hardware_fingerprint,
            "port": self.config.port,
            "is_gpu_worker": self.config.is_gpu_worker,
            "gpu_info": self.config.gpu_info,
            "metadata": self.metadata,
            "preferred_ip": self.metadata.get("tailscale_ip", ""),
        }
        try:
            res = await client.post(url, json=payload, headers=self.auth_headers, timeout=10.0)
            if res.status_code == 200:
                self.is_registered = True
                logger.info("Registro exitoso en el Hub como '%s' (%s)", self.config.node_name, self.node_id)
                return True, "Registro exitoso."
            else:
                logger.warning("Fallo al registrar nodo (%s): %s", res.status_code, res.text)
                return False, f"HTTP {res.status_code}: {res.text}"
        except Exception as e:
            logger.warning("No se pudo conectar con el Hub en %s: %s", url, e)
            return False, str(e)

    async def send_heartbeat(self, client: httpx.AsyncClient) -> bool:
        """Envia senal de vida periodica al Hub."""
        url = f"{self.config.hub_url.rstrip('/')}/api/v1/nodes/heartbeat"
        payload = {
            "node_id": self.node_id,
            "hardware_fingerprint": self.hardware_fingerprint,
            "is_gpu_worker": self.config.is_gpu_worker,
            "gpu_info": self.config.gpu_info,
            "preferred_ip": self.metadata.get("tailscale_ip", ""),
        }
        try:
            res = await client.post(url, json=payload, headers=self.auth_headers, timeout=8.0)
            if res.status_code == 200:
                return True
            elif res.status_code == 404:
                # El Hub se reinicio o perdio el registro: re-registrar
                logger.info("Hub respondio 404 a heartbeat. Reintentando registro...")
                self.is_registered = False
                await self.register(client)
        except Exception as e:
            logger.debug("Fallo de heartbeat: %s", e)
        return False

    async def send_telemetry(self, client: httpx.AsyncClient) -> bool:
        """Recolecta y despacha telemetria de recursos y contenedores al Hub."""
        url = f"{self.config.hub_url.rstrip('/')}/api/v1/telemetry/report"
        telemetry_data = collect_host_telemetry(self.config.services)
        payload = {
            "node_id": self.node_id,
            "hardware_fingerprint": self.hardware_fingerprint,
            **telemetry_data,
        }
        try:
            res = await client.post(url, json=payload, headers=self.auth_headers, timeout=10.0)
            return res.status_code == 200
        except Exception as e:
            logger.debug("Fallo de reporte de telemetria: %s", e)
            return False

    async def run_heartbeat_loop(self, client: httpx.AsyncClient, stop_event: asyncio.Event) -> None:
        """Bucle en segundo plano para emision de latidos."""
        while not stop_event.is_set():
            if not self.is_registered:
                await self.register(client)
            else:
                await self.send_heartbeat(client)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.config.heartbeat_interval_sec)
            except asyncio.TimeoutError:
                pass

    async def run_telemetry_loop(self, client: httpx.AsyncClient, stop_event: asyncio.Event) -> None:
        """Bucle en segundo plano para emision de telemetria."""
        while not stop_event.is_set():
            if self.is_registered:
                await self.send_telemetry(client)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.config.telemetry_interval_sec)
            except asyncio.TimeoutError:
                pass

    async def run_agent(self, stop_event: asyncio.Event = None) -> None:
        """Ejecuta el agente satelite completo hasta recibir senal de parada."""
        if stop_event is None:
            stop_event = asyncio.Event()

        logger.info("Iniciando Jota Satelite en modo '%s'...", self.config.mode)
        logger.info("Nodo ID: %s | Hostname: %s", self.node_id, self.config.node_name)
        logger.info("Destino Hub: %s", self.config.hub_url)

        async with httpx.AsyncClient() as http_client:
            # Intentar registro inicial
            await self.register(http_client)

            # Lanzar tareas concurrentes de latido y telemetria
            tasks = [
                asyncio.create_task(self.run_heartbeat_loop(http_client, stop_event)),
                asyncio.create_task(self.run_telemetry_loop(http_client, stop_event)),
            ]
            try:
                await asyncio.gather(*tasks)
            except asyncio.CancelledError:
                pass


def main() -> None:
    """Punto de entrada CLI para ejecutar el satelite como demonio o servicio systemd."""
    parser = argparse.ArgumentParser(description="Jota Satelite - Cliente de Escritorio y Telemetria")
    parser.add_argument("--mode", choices=["desktop", "headless"], help="Perfil de ejecucion")
    parser.add_argument("--hub-url", help="URL del servidor Jota Hub (ej: http://192.168.1.100:8765)")
    parser.add_argument("--token", help="Token secreto de conexion al Hub (X-Jota-Token)")
    parser.add_argument("--name", help="Nombre descriptivo para este satelite en el cluster")
    parser.add_argument("--status", action="store_true", help="Muestra informacion de identidad y hardware")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if args.status:
        meta = get_node_metadata()
        has_gpu, gpu_info = detect_local_gpu()
        print("--- Identidad Jota Satelite ---")
        print(f"Node ID:       {meta['node_id']}")
        print(f"Hostname:      {meta['hostname']}")
        print(f"SO / Kernel:   {meta['os']} {meta['release']} ({meta['arch']})")
        print(f"MAC Primaria:  {meta['mac_primary']}")
        print(f"Tailscale:     {'Activo' if meta['has_tailscale'] else 'Inactivo'}")
        print(f"Aceleracion:   {gpu_info if has_gpu else 'CPU unicamente'}")
        sys.exit(0)

    # Cargar configuracion base
    config = SatelliteConfig.load_from_file()

    # Sobrescribir con argumentos CLI si fueron provistos
    if args.mode:
        config.mode = args.mode
    if args.hub_url:
        config.hub_url = args.hub_url
    if args.token:
        config.hub_token = args.token
    if args.name:
        config.node_name = args.name

    client = SatelliteClient(config)
    stop_event = asyncio.Event()

    try:
        asyncio.run(client.run_agent(stop_event))
    except (KeyboardInterrupt, SystemExit):
        logger.info("Deteniendo satelite...")
        stop_event.set()


if __name__ == "__main__":
    main()

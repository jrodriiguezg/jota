"""
Herramientas del cluster y gestion multi-servidor para el asistente Jota.
Permite consultar el estado de los satelites, monitorizacion de recursos
y contenedores de todos los servidores registrados en el Hub.
"""

import logging
from pathlib import Path
from typing import Any

from bridge.config import BRIDGE_API_KEY, HUB_DB_PATH
from jota.hub_db import HubDatabase

logger = logging.getLogger("jota.tools.cluster")


def _get_hub_db() -> HubDatabase:
    """Instancia el acceso a la base de datos local del Hub."""
    return HubDatabase(HUB_DB_PATH, secret_key=BRIDGE_API_KEY)


def query_cluster_nodes(status_filter: str = "all") -> tuple[bool, str]:
    """
    Consulta los nodos y satelites registrados en el cluster.
    Devuelve un resumen para el usuario.
    """
    try:
        db = _get_hub_db()
        nodes = db.list_nodes(offline_timeout_seconds=45.0)
    except Exception as e:
        logger.error("Error al consultar nodos del cluster: %s", e)
        return False, f"No se pudo consultar el cluster de servidores: {e}"

    if not nodes:
        return True, "No hay ningun nodo ni satelite registrado en el cluster actualmente."

    online_nodes = [n for n in nodes if n["status"] == "online"]
    offline_nodes = [n for n in nodes if n["status"] == "offline"]

    parts = []
    if online_nodes:
        online_desc = []
        for n in online_nodes:
            gpu_str = f" con {n['gpu_info']}" if n.get("is_gpu_worker") and n.get("gpu_info") else ""
            mode_str = "escritorio" if n.get("mode") == "desktop" else "monitorizacion"
            online_desc.append(f"{n['name']} ({mode_str}{gpu_str})")
        parts.append(f"Activos: {', '.join(online_desc)}.")

    if offline_nodes and status_filter != "online":
        offline_desc = [n["name"] for n in offline_nodes]
        parts.append(f"Desconectados: {', '.join(offline_desc)}.")

    return True, f"Nodos del cluster: {' '.join(parts)}"


def query_node_telemetry(node_name_or_id: str) -> tuple[bool, str]:
    """
    Consulta las metricas de uso y salud de un nodo o servidor especifico.
    """
    if not node_name_or_id:
        return False, "Debes indicar el nombre del servidor o satelite a consultar."

    try:
        db = _get_hub_db()
        nodes = db.list_nodes()
    except Exception as e:
        return False, f"Error al acceder a la base de datos del cluster: {e}"

    target_node = None
    query_lower = node_name_or_id.lower().strip()

    for n in nodes:
        if n["node_id"].lower() == query_lower or query_lower in n["name"].lower():
            target_node = n
            break

    if not target_node:
        nombres_disponibles = ", ".join(n["name"] for n in nodes) or "ninguno"
        return False, f"No encontre ningun servidor llamado '{node_name_or_id}'. Disponibles: {nombres_disponibles}."

    node_id = target_node["node_id"]
    telemetry = db.get_latest_telemetry(node_id)
    if not telemetry:
        return True, f"El servidor '{target_node['name']}' esta registrado pero aun no ha enviado datos de telemetria."

    cpu = telemetry.get("cpu_percent", 0.0)
    ram = telemetry.get("ram_percent", 0.0)
    disk = telemetry.get("disk_percent", 0.0)
    containers = telemetry.get("containers", [])

    containers_summary = ""
    if containers:
        running_cnt = sum(1 for c in containers if c.get("status") in ("running", "up"))
        containers_summary = f" y {running_cnt} de {len(containers)} contenedores en ejecucion"

    return True, (
        f"El servidor '{target_node['name']}' esta con {cpu:.1f}% de CPU, "
        f"{ram:.1f}% de memoria RAM, disco al {disk:.1f}%{containers_summary}."
    )


def query_cluster_containers(name_filter: str = "") -> tuple[bool, str]:
    """
    Consolida la lista de contenedores Docker y Podman que corren en cualquier nodo del cluster.
    """
    try:
        db = _get_hub_db()
        all_containers = db.get_all_containers_summary()
    except Exception as e:
        return False, f"Error al consultar contenedores del cluster: {e}"

    if not all_containers:
        return True, "No se encontraron contenedores activos en ningun servidor monitorizado del cluster."

    if name_filter:
        clean_f = name_filter.lower().strip()
        filtered = [c for c in all_containers if clean_f in c.get("name", "").lower()]
        if not filtered:
            return True, f"No se encontro ningun contenedor con el nombre '{name_filter}'."
        all_containers = filtered

    descriptions = []
    for c in all_containers[:10]:  # Limitar a los 10 primeros para no saturar voz
        node_name = c.get("node_name", "servidor")
        name = c.get("name", "sin_nombre")
        status = c.get("status", "desconocido")
        descriptions.append(f"{name} en {node_name} ({status})")

    return True, f"Contenedores monitorizados: {', '.join(descriptions)}."

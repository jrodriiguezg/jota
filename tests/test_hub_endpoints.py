"""
Pruebas de integracion para los endpoints del cluster y orquestador en Jota Hub (bridge/server.py).
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from bridge.config import BRIDGE_API_KEY
from bridge.server import app

client = TestClient(app)
AUTH_HEADERS = {"X-Jota-Token": str(BRIDGE_API_KEY)}


def test_health_endpoint():
    """Verifica que el endpoint /health devuelve metadatos de Jota Hub y nodos."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] in ("jota-hub", "jota-bridge")
    assert data.get("hub_mode") is True
    assert "nodes_total" in data
    assert "nodes_online" in data
    assert "gpu_worker_available" in data


def test_cluster_endpoints_require_auth():
    """Verifica que los endpoints del cluster exigen autenticacion valida."""
    # Sin cabecera
    r1 = client.get("/api/v1/nodes/list")
    assert r1.status_code == 401

    # Con clave erronea
    r2 = client.get("/api/v1/nodes/list", headers={"X-Jota-Token": "clave_incorrecta"})
    assert r2.status_code == 401


def test_register_and_list_nodes():
    """Verifica el flujo de registro de un nodo y posterior listado."""
    payload = {
        "node_id": "node_test_endpoint_1",
        "name": "estacion-diseno",
        "mode": "desktop",
        "hardware_fingerprint": "f" * 64,
        "port": 8765,
        "is_gpu_worker": True,
        "gpu_info": "NVIDIA RTX 5070",
        "metadata": {"os": "Linux", "arch": "x86_64"},
    }

    # Registro exitoso
    res = client.post("/api/v1/nodes/register", json=payload, headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # Listar nodos
    res_list = client.get("/api/v1/nodes/list", headers=AUTH_HEADERS)
    assert res_list.status_code == 200
    nodes = res_list.json()["nodes"]
    target = next((n for n in nodes if n["node_id"] == "node_test_endpoint_1"), None)
    assert target is not None
    assert target["name"] == "estacion-diseno"
    assert target["is_gpu_worker"] == 1


def test_register_conflict_rejection():
    """Verifica rechazo con 400 ante intento de registrar mismo node_id con huella distinta."""
    payload1 = {
        "node_id": "node_legit_satellite",
        "name": "satelite-real",
        "mode": "headless",
        "hardware_fingerprint": "1" * 64,
    }
    r1 = client.post("/api/v1/nodes/register", json=payload1, headers=AUTH_HEADERS)
    assert r1.status_code == 200

    payload_fake = {
        "node_id": "node_legit_satellite",
        "name": "satelite-impostor",
        "mode": "headless",
        "hardware_fingerprint": "2" * 64,
    }
    r2 = client.post("/api/v1/nodes/register", json=payload_fake, headers=AUTH_HEADERS)
    assert r2.status_code == 400
    assert "Conflicto de hardware" in r2.json()["detail"]


def test_heartbeat_and_telemetry_flow():
    """Verifica recepcion de heartbeat y almacenamiento de reporte de telemetria."""
    # 1. Registrar nodo
    reg = client.post(
        "/api/v1/nodes/register",
        json={
            "node_id": "node_heartbeat_flow",
            "name": "servidor-backup",
            "mode": "headless",
            "hardware_fingerprint": "3" * 64,
        },
        headers=AUTH_HEADERS,
    )
    assert reg.status_code == 200

    # 2. Enviar heartbeat
    hb = client.post(
        "/api/v1/nodes/heartbeat",
        json={"node_id": "node_heartbeat_flow"},
        headers=AUTH_HEADERS,
    )
    assert hb.status_code == 200
    assert hb.json()["status"] == "ok"

    # 3. Reportar telemetria
    telem = client.post(
        "/api/v1/telemetry/report",
        json={
            "node_id": "node_heartbeat_flow",
            "cpu_percent": 24.5,
            "ram_percent": 60.1,
            "disk_percent": 45.0,
            "containers": [{"name": "restic", "status": "running"}],
            "systemd_services": ["sshd.service"],
        },
        headers=AUTH_HEADERS,
    )
    assert telem.status_code == 200
    assert telem.json()["status"] == "ok"

    # 4. Comprobar cluster_status consolidado
    status_res = client.get("/api/v1/homelab/cluster_status", headers=AUTH_HEADERS)
    assert status_res.status_code == 200
    data = status_res.json()
    assert data["nodes_total"] >= 1
    assert any(c["name"] == "restic" for c in data["containers"])


def test_assistant_query_gpu_worker_offload_and_fallback():
    """Verifica que el endpoint /api/v1/assistant/query delega o procesa adecuadamente con fallback."""
    with patch("bridge.server.hub_db.get_active_gpu_worker") as mock_gpu:
        mock_gpu.return_value = {
            "name": "estacion-rtx",
            "ip_address": "127.0.0.1",
            "port": 9999,
        }
        with patch("bridge.server.process_remote_text") as mock_local:
            mock_local.return_value = {"text": "Respuesta local del Hub", "audio_url": None}
            res = client.post(
                "/api/v1/assistant/query",
                json={"prompt": "Hola asistente", "prefer_gpu": True},
                headers=AUTH_HEADERS,
            )
            assert res.status_code == 200
            assert res.json()["text"] == "Respuesta local del Hub"
            assert mock_local.called

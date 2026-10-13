"""
Pruebas unitarias para la base de datos de Jota Hub (jota.hub_db).
"""

import time
from pathlib import Path

import pytest

from jota.hub_db import HubDatabase


@pytest.fixture
def test_db(tmp_path: Path) -> HubDatabase:
    """Crea una base de datos temporal para pruebas aisladas."""
    db_file = tmp_path / "test_hub.db"
    return HubDatabase(db_file, secret_key="test_cluster_secret_key")


def test_register_and_get_node(test_db: HubDatabase):
    """Verifica el registro exitoso de un nodo nuevo."""
    ok, msg = test_db.register_or_update_node(
        node_id="node_0123456789abcdef",
        name="estacion-trabajo",
        mode="desktop",
        hardware_fingerprint="a" * 64,
        ip_address="192.168.1.135",
        is_gpu_worker=True,
        gpu_info="NVIDIA RTX 5070",
    )
    assert ok is True
    assert "registrado exitosamente" in msg

    node = test_db.get_node("node_0123456789abcdef")
    assert node is not None
    assert node["name"] == "estacion-trabajo"
    assert node["mode"] == "desktop"
    assert node["is_gpu_worker"] == 1
    assert node["gpu_info"] == "NVIDIA RTX 5070"
    assert node["status"] == "online"


def test_reject_spoofed_node_registration(test_db: HubDatabase):
    """Verifica que se rechaza el registro si la huella de hardware difiere."""
    # Primer registro legitimo
    test_db.register_or_update_node(
        node_id="node_1111222233334444",
        name="servidor-nas",
        mode="headless",
        hardware_fingerprint="a" * 64,
        ip_address="192.168.1.200",
    )

    # Intento de suplantacion con huella distinta
    ok, msg = test_db.register_or_update_node(
        node_id="node_1111222233334444",
        name="servidor-nas-falso",
        mode="headless",
        hardware_fingerprint="b" * 64,
        ip_address="192.168.1.201",
    )
    assert ok is False
    assert "Conflicto de hardware" in msg


def test_heartbeat_and_offline_detection(test_db: HubDatabase):
    """Verifica la actualizacion de latido y la deteccion de nodos caidos."""
    test_db.register_or_update_node(
        node_id="node_heartbeat_test",
        name="nodo-prueba",
        mode="desktop",
        hardware_fingerprint="c" * 64,
        ip_address="192.168.1.10",
    )

    # Inmediatamente debe estar online
    nodes = test_db.list_nodes(offline_timeout_seconds=5.0)
    assert len(nodes) == 1
    assert nodes[0]["status"] == "online"

    # Simular paso del tiempo estableciendo last_heartbeat en el pasado
    with test_db._get_connection() as conn:
        conn.execute(
            "UPDATE nodes SET last_heartbeat = ? WHERE node_id = ?",
            (time.time() - 10.0, "node_heartbeat_test"),
        )

    # Con timeout de 5 segundos debe reportarse offline
    nodes = test_db.list_nodes(offline_timeout_seconds=5.0)
    assert nodes[0]["status"] == "offline"

    # Enviar nuevo heartbeat
    ok = test_db.record_heartbeat("node_heartbeat_test")
    assert ok is True
    nodes = test_db.list_nodes(offline_timeout_seconds=5.0)
    assert nodes[0]["status"] == "online"


def test_active_gpu_worker_detection(test_db: HubDatabase):
    """Verifica la deteccion de un servidor secundario con GPU activo."""
    # Sin workers registrados
    assert test_db.get_active_gpu_worker() is None

    # Registrar worker con GPU
    test_db.register_or_update_node(
        node_id="node_gpu_worker_1",
        name="rtx-worker",
        mode="desktop",
        hardware_fingerprint="d" * 64,
        ip_address="192.168.1.150",
        is_gpu_worker=True,
        gpu_info="NVIDIA RTX 5070 12GB",
    )

    worker = test_db.get_active_gpu_worker(offline_timeout_seconds=10.0)
    assert worker is not None
    assert worker["node_id"] == "node_gpu_worker_1"
    assert worker["gpu_info"] == "NVIDIA RTX 5070 12GB"


def test_record_telemetry_and_containers(test_db: HubDatabase):
    """Verifica el almacenamiento de telemetria de contenedores y metricas de host."""
    test_db.register_or_update_node(
        node_id="node_nas_telemetry",
        name="truenas",
        mode="headless",
        hardware_fingerprint="e" * 64,
        ip_address="192.168.1.200",
    )

    telemetry_data = {
        "cpu_percent": 15.5,
        "ram_percent": 42.1,
        "disk_percent": 68.0,
        "containers": [
            {"name": "navidrome", "status": "running", "image": "deluan/navidrome"},
            {"name": "vaultwarden", "status": "running", "image": "vaultwarden/server"},
        ],
        "systemd_services": ["docker.service", "sshd.service"],
    }

    ok = test_db.record_telemetry("node_nas_telemetry", telemetry_data)
    assert ok is True

    latest = test_db.get_latest_telemetry("node_nas_telemetry")
    assert latest is not None
    assert latest["cpu_percent"] == 15.5
    assert len(latest["containers"]) == 2
    assert latest["containers"][0]["name"] == "navidrome"

    # Verificacion del resumen consolidado de contenedores
    all_containers = test_db.get_all_containers_summary()
    assert len(all_containers) == 2
    assert all_containers[0]["node_name"] == "truenas"


def test_encrypted_cluster_secrets(test_db: HubDatabase):
    """Verifica almacenamiento cifrado en reposo para claves del cluster."""
    secret_value = "super_secret_homelab_token_9988"
    test_db.set_secret("navidrome_token", secret_value)

    # Verificar que en la base de datos SQLite no esta en texto plano
    with test_db._get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT encrypted_value FROM cluster_secrets WHERE key = 'navidrome_token'")
        raw_val = cur.fetchone()["encrypted_value"]
        assert raw_val.startswith("enc:v1:")
        assert secret_value not in raw_val

    # Descifrado correcto
    decrypted = test_db.get_secret("navidrome_token")
    assert decrypted == secret_value

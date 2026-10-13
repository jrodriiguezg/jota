"""
Pruebas unitarias para el cliente y recolector de satelite (jota.satellite).
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jota.satellite import (
    SatelliteClient,
    SatelliteConfig,
    collect_host_telemetry,
    detect_local_gpu,
)


def test_satellite_config_defaults():
    """Verifica la inicializacion de configuracion con valores por defecto."""
    cfg = SatelliteConfig(node_name="test-node", hub_token="token123")
    assert cfg.node_name == "test-node"
    assert cfg.mode == "desktop"
    assert cfg.hub_url == "http://127.0.0.1:8765"
    assert cfg.hub_token == "token123"
    assert cfg.heartbeat_interval_sec == 15.0
    assert cfg.telemetry_interval_sec == 30.0


def test_satellite_config_save_and_load(tmp_path: Path):
    """Verifica la persistencia y lectura de configuracion YAML."""
    config_file = tmp_path / "satelite.yaml"
    original = SatelliteConfig(
        node_name="servidor-nas",
        mode="headless",
        hub_url="http://192.168.1.100:8765",
        hub_token="secret_key_456",
        port=8765,
        heartbeat_interval_sec=20.0,
        telemetry_interval_sec=45.0,
        services=["sshd", "docker"],
    )
    original.save_to_file(config_file)
    assert config_file.is_file()

    loaded = SatelliteConfig.load_from_file(config_file)
    assert loaded.node_name == "servidor-nas"
    assert loaded.mode == "headless"
    assert loaded.hub_url == "http://192.168.1.100:8765"
    assert loaded.hub_token == "secret_key_456"
    assert loaded.heartbeat_interval_sec == 20.0
    assert loaded.telemetry_interval_sec == 45.0
    assert loaded.services == ["sshd", "docker"]


def test_detect_local_gpu_when_missing():
    """Verifica degradacion elegante cuando nvidia-smi no esta disponible."""
    with patch("shutil.which", return_value=None):
        has_gpu, info = detect_local_gpu()
        assert has_gpu is False
        assert info == ""


def test_detect_local_gpu_when_present():
    """Verifica deteccion de GPU cuando nvidia-smi reporta datos."""
    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stdout = "NVIDIA GeForce RTX 5070, 8151\n"
    with patch("shutil.which", return_value="/usr/bin/nvidia-smi"):
        with patch("subprocess.run", return_value=mock_run):
            has_gpu, info = detect_local_gpu()
            assert has_gpu is True
            assert "RTX 5070" in info
            assert "8151 MB" in info


def test_collect_host_telemetry():
    """Verifica que la recoleccion de telemetria produce la estructura esperada."""
    data = collect_host_telemetry(services=["sshd"])
    assert "cpu_percent" in data
    assert "ram_percent" in data
    assert "disk_percent" in data
    assert "containers" in data
    assert "systemd_services" in data
    assert isinstance(data["containers"], list)
    assert isinstance(data["systemd_services"], list)


@pytest.mark.asyncio
async def test_satellite_client_register_success():
    """Verifica el flujo de registro exitoso en el Hub."""
    cfg = SatelliteConfig(node_name="mi-nodo", hub_token="token_valido")
    client = SatelliteClient(cfg)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok"}

    mock_http = AsyncMock()
    mock_http.post.return_value = mock_resp

    ok, msg = await client.register(mock_http)
    assert ok is True
    assert client.is_registered is True
    assert mock_http.post.called


@pytest.mark.asyncio
async def test_satellite_client_heartbeat_and_reregister():
    """Verifica emision de latido y re-registro ante respuesta 404 del Hub."""
    cfg = SatelliteConfig(node_name="mi-nodo", hub_token="token_valido")
    client = SatelliteClient(cfg)
    client.is_registered = True

    # 1. Heartbeat 200 OK
    mock_ok = MagicMock()
    mock_ok.status_code = 200
    mock_http = AsyncMock()
    mock_http.post.return_value = mock_ok

    success = await client.send_heartbeat(mock_http)
    assert success is True

    # 2. Heartbeat 404 (Hub reiniciado)
    mock_404 = MagicMock()
    mock_404.status_code = 404
    mock_http.post.return_value = mock_404

    with patch.object(client, "register", new_callable=AsyncMock) as mock_reg:
        mock_reg.return_value = (True, "OK")
        await client.send_heartbeat(mock_http)
        assert client.is_registered is False
        assert mock_reg.called


@pytest.mark.asyncio
async def test_satellite_client_send_telemetry():
    """Verifica emision de reporte de telemetria al Hub."""
    cfg = SatelliteConfig(node_name="mi-nodo", hub_token="token_valido")
    client = SatelliteClient(cfg)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_http = AsyncMock()
    mock_http.post.return_value = mock_resp

    success = await client.send_telemetry(mock_http)
    assert success is True
    assert mock_http.post.called

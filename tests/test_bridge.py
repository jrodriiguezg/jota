"""
Pruebas unitarias para Jota Bridge:
- Operaciones del PC (metricas, seguridad de archivos, portapapeles)
- Gestor de conexiones con dispositivos Android (PhoneConnectionManager)
- Herramienta de control telefonico (jota/tools/phone.py)
- Endpoints REST y WebSocket de FastAPI (bridge/server.py)
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from bridge.config import BRIDGE_API_KEY
from bridge.pc_ops import (
    get_cpu_load,
    get_disk_info,
    get_memory_info,
    get_system_status,
    get_uptime_seconds,
    resolve_safe_file_path,
)
from bridge.phone_manager import PhoneConnectionManager
from bridge.server import app
from jota.tools.phone import phone_control
from jota.tools.router import execute_tool, parse_llm_tool_call


class TestPCOperations:
    """Verifica las lecturas de hardware y resolucion segura de archivos."""

    def test_cpu_load(self):
        cpu = get_cpu_load()
        assert "load_1m" in cpu
        assert "cpu_cores" in cpu
        assert cpu["cpu_cores"] >= 1

    def test_memory_info(self):
        mem = get_memory_info()
        assert "total_mb" in mem
        assert "used_mb" in mem
        assert "percent_used" in mem
        assert mem["total_mb"] >= 0

    def test_disk_info(self):
        disk = get_disk_info()
        assert "total_gb" in disk
        assert "percent_used" in disk
        assert disk["total_gb"] > 0

    def test_uptime_seconds(self):
        uptime = get_uptime_seconds()
        assert isinstance(uptime, int)
        assert uptime >= 0

    def test_system_status_structure(self):
        status = get_system_status()
        assert "cpu" in status
        assert "memory" in status
        assert "disk" in status
        assert "uptime_seconds" in status
        assert "active_window" in status

    def test_resolve_safe_file_success(self):
        # Archivo existente en el repo del usuario
        readme = Path("README.md").resolve()
        resolved = resolve_safe_file_path(str(readme))
        assert resolved == readme

    def test_resolve_safe_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            resolve_safe_file_path("/tmp/archivo_inexistente_123456789.txt")

    def test_resolve_safe_file_forbidden_pattern(self):
        with pytest.raises((ValueError, FileNotFoundError)):
            resolve_safe_file_path("~/.ssh/id_rsa")

    def test_resolve_safe_file_empty(self):
        with pytest.raises(ValueError):
            resolve_safe_file_path("")


class TestPhoneManager:
    """Verifica la logica del gestor de conexiones con Android."""

    def test_initial_state(self):
        mgr = PhoneConnectionManager()
        assert not mgr.is_connected()
        assert mgr.list_connected_devices() == []
        status = mgr.get_device_status()
        assert status["device_id"] is None

    def test_status_update(self):
        mgr = PhoneConnectionManager()
        mgr.update_device_status("test_phone", {"battery": 88, "is_charging": True})
        status = mgr.get_device_status("test_phone")
        assert status["battery"] == 88
        assert status["is_charging"] is True


class TestPhoneTool:
    """Verifica la herramienta de voz jota/tools/phone.py y su integracion con el LLM."""

    def test_phone_control_status_unconnected(self):
        msg = phone_control("status")
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_phone_control_unknown_action(self):
        msg = phone_control("accion_inexistente")
        assert "no reconocida" in msg or "no esta activo" in msg

    def test_router_parse_phone_control(self):
        out = "TOOL: phone_control(action='ring')\nHaciendo sonar tu telefono."
        parsed = parse_llm_tool_call(out)
        assert parsed is not None
        assert parsed.name == "phone_control"
        assert parsed.args["action"] == "ring"

    def test_router_parse_phone_control_alias(self):
        out = "TOOL: phone(action='status')"
        parsed = parse_llm_tool_call(out)
        assert parsed is not None
        assert parsed.name == "phone_control"
        assert parsed.args["action"] == "status"

    def test_execute_tool_phone_control(self):
        success, msg = execute_tool("phone_control", {"action": "ring"})
        assert success is True
        assert len(msg) > 0


class TestBridgeAPI:
    """Verifica los endpoints REST y WebSocket de FastAPI con TestClient."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "online"
        assert data["service"] == "jota-bridge"

    def test_auth_denied(self, client):
        resp = client.get("/api/v1/pc/status")
        assert resp.status_code == 401

    def test_pc_status_authorized(self, client):
        resp = client.get("/api/v1/pc/status", headers={"X-Bridge-Key": BRIDGE_API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert "cpu" in data
        assert "memory" in data

    def test_pc_clipboard(self, client):
        resp = client.get("/api/v1/pc/clipboard", headers={"X-Bridge-Key": BRIDGE_API_KEY})
        assert resp.status_code == 200
        assert "text" in resp.json()

    def test_pc_file_download_safe(self, client):
        resp = client.get(
            "/api/v1/pc/file",
            params={"path": "README.md"},
            headers={"X-Bridge-Key": BRIDGE_API_KEY},
        )
        assert resp.status_code == 200
        assert "Jota" in resp.text

    def test_pc_file_download_forbidden(self, client):
        resp = client.get(
            "/api/v1/pc/file",
            params={"path": "/etc/shadow"},
            headers={"X-Bridge-Key": BRIDGE_API_KEY},
        )
        assert resp.status_code in (403, 404)

    def test_text_ask(self, client):
        with patch("bridge.voice_pipeline.ask_llm", return_value="Todo funciona bien en el PC."):
            resp = client.post(
                "/api/v1/text/ask",
                json={"prompt": "¿Como esta el PC?", "generate_audio": False},
                headers={"X-Bridge-Key": BRIDGE_API_KEY},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert "Todo funciona bien" in data["response_text"]

    def test_phone_websocket_auth_failed(self, client):
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/phone?token=token_invalido"):
                pass

    def test_phone_websocket_success(self, client):
        with client.websocket_connect(f"/ws/phone?token={BRIDGE_API_KEY}") as ws:
            init_msg = ws.receive_json()
            assert init_msg["event"] == "connected"
            assert "pc_status" in init_msg

"""
Pruebas unitarias para Jota Bridge:
- Operaciones del PC (metricas, seguridad de archivos, portapapeles)
- Gestor de conexiones con dispositivos Android (PhoneConnectionManager)
- Herramienta de control telefonico (jota/tools/phone.py)
- Endpoints REST y WebSocket de FastAPI (bridge/server.py)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def test_phone_control_torch_and_silent(self):
        msg_torch = phone_control("torch", "on")
        assert isinstance(msg_torch, str)
        msg_silent = phone_control("silent", "on")
        assert isinstance(msg_silent, str)


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

    def test_pc_screenshots_list(self, client):
        resp = client.get("/api/v1/pc/screenshots", headers={"X-Bridge-Key": BRIDGE_API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert "screenshots" in data
        assert isinstance(data["screenshots"], list)

    def test_pc_screenshots_file_not_found(self, client):
        resp = client.get(
            "/api/v1/pc/screenshots/file",
            params={"name": "no_existe_captura_123.png"},
            headers={"X-Bridge-Key": BRIDGE_API_KEY},
        )
        assert resp.status_code == 404

    @patch("bridge.server.capture_screen_bytes")
    def test_pc_capture_screenshot(self, mock_capture, client):
        mock_capture.return_value = b"\x89PNG\r\n\x1a\nfake"
        resp = client.post(
            "/api/v1/pc/screenshots/capture",
            headers={"X-Bridge-Key": BRIDGE_API_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "screenshots" in data

    def test_battery_and_media_in_system_status(self):
        from bridge.pc_ops import get_battery_status, get_media_status, get_system_status

        bat = get_battery_status()
        assert "present" in bat
        assert "charging" in bat

        media = get_media_status()
        assert "available" in media
        assert "status" in media

        status = get_system_status()
        assert "battery" in status
        assert "media" in status

    def test_resolve_safe_file_null_byte_and_sensitive(self):
        with pytest.raises(ValueError):
            resolve_safe_file_path("test\x00file.txt")

        with pytest.raises((ValueError, FileNotFoundError)):
            resolve_safe_file_path("~/.bash_history")

        with pytest.raises((ValueError, FileNotFoundError)):
            resolve_safe_file_path("~/.aws/credentials")

    def test_auth_rate_limiting(self, client):
        import bridge.server as srv
        srv._failed_auth_log.clear()

        # Generar intentos fallidos
        for _ in range(srv.AUTH_RATE_LIMIT_MAX_FAILURES):
            resp = client.get("/api/v1/pc/status", headers={"X-Bridge-Key": "bad_key"})
            assert resp.status_code in (401, 429)

        # Siguiente intento debe ser 429 Too Many Requests
        resp = client.get("/api/v1/pc/status", headers={"X-Bridge-Key": "bad_key"})
        assert resp.status_code == 429

        srv._failed_auth_log.clear()

    def test_phone_websocket_actions(self, client):
        with client.websocket_connect(f"/ws/phone?token={BRIDGE_API_KEY}") as ws:
            init = ws.receive_json()
            assert init["event"] == "connected"

            # Enviar ping
            ws.send_json({"event": "ping"})
            pong = ws.receive_json()
            assert pong["event"] == "pong"

            # Solicitar estado del PC
            ws.send_json({"event": "get_status"})
            status_msg = ws.receive_json()
            assert status_msg["event"] == "pc_status"
            assert "payload" in status_msg

            # Enviar accion rapida pc_action (mute)
            with patch("bridge.server.execute_pc_action", return_value=(True, "Audio silenciado.")):
                ws.send_json({"event": "pc_action", "payload": {"action": "mute"}})
                action_msg = ws.receive_json()
                assert action_msg["event"] == "pc_action_result"
                assert action_msg["payload"]["success"] is True

    def test_cleanup_old_temp_files(self, tmp_path, monkeypatch):
        import time

        from bridge.voice_pipeline import cleanup_old_temp_files

        monkeypatch.setattr("bridge.voice_pipeline.BRIDGE_TEMP_DIR", tmp_path)

        old_file = tmp_path / "remote_in_old.wav"
        old_file.write_text("old")
        # Forzar mtime antiguo (hace 20 minutos)
        past_time = time.time() - 1200
        import os
        os.utime(old_file, (past_time, past_time))

        recent_file = tmp_path / "remote_out_recent.wav"
        recent_file.write_text("recent")

        deleted = cleanup_old_temp_files(max_age_seconds=900)
        assert deleted == 1
        assert not old_file.exists()
        assert recent_file.exists()

    def test_nearby_channels_and_endpoints(self, client):
        from bridge.discovery import get_nearby_channels_status

        status = get_nearby_channels_status(port=8765)
        assert "wifi_lan" in status
        assert "usb_cable" in status
        assert "bluetooth" in status

        # Endpoint GET /api/v1/pc/channels
        resp = client.get("/api/v1/pc/channels", headers={"X-Bridge-Key": "jota-secret-tailscale-key"})
        assert resp.status_code == 200
        data = resp.json()
        assert "wifi_lan" in data
        assert "usb_cable" in data

    @patch("bridge.discovery.subprocess.run")
    @patch("bridge.discovery.shutil.which")
    def test_setup_adb_reverse(self, mock_which, mock_run):
        from bridge.discovery import setup_adb_reverse

        # 1. ADB no instalado
        mock_which.return_value = None
        ok, msg = setup_adb_reverse(port=8765)
        assert ok is False
        assert "no esta instalado" in msg.lower()

        # 2. ADB instalado pero sin dispositivos
        mock_which.return_value = "/usr/bin/adb"
        res_no_dev = MagicMock()
        res_no_dev.stdout = "List of devices attached\n\n"
        mock_run.return_value = res_no_dev
        ok, msg = setup_adb_reverse(port=8765)
        assert ok is False
        assert "no se detecto" in msg.lower()

        # 3. Dispositivo conectado correctamente
        res_devices = MagicMock()
        res_devices.stdout = "List of devices attached\nemulator-5554\tdevice\n\n"
        res_reverse = MagicMock()
        res_reverse.returncode = 0
        mock_run.side_effect = [res_devices, res_reverse]

        ok, msg = setup_adb_reverse(port=8765)
        assert ok is True
        assert "emulator-5554" in msg
        assert "http://127.0.0.1:8765" in msg

    def test_mdns_registration_lifecycle(self):
        import asyncio

        from bridge.discovery import register_mdns_service, unregister_mdns_service

        async def _run():
            handle = await register_mdns_service(port=8765)
            assert handle is not None
            await unregister_mdns_service(handle)

        asyncio.run(_run())

    def test_pc_network_endpoint(self, client):
        resp = client.get("/api/v1/pc/network", headers={"X-Bridge-Key": BRIDGE_API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert "hostname" in data
        assert "primary_mac" in data
        assert "interfaces" in data

    def test_bridge_pairing_endpoint(self, client):
        resp = client.get("/api/v1/bridge/pairing")
        assert resp.status_code == 200
        data = resp.json()
        assert "url" in data
        assert "api_key" in data
        assert "mac" in data





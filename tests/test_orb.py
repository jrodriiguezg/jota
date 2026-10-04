"""Pruebas unitarias para el indicador visual (orbe de pantalla Wayland)."""

from unittest.mock import MagicMock, patch

import pytest

from jota.ui.client import OrbClient


class TestOrbClient:
    """Verifica el cliente IPC del orbe flotante."""

    def test_client_init(self, tmp_path):
        sock_file = tmp_path / "test_orb.sock"
        client = OrbClient(socket_path=sock_file, auto_start=False)
        assert client.socket_path == sock_file
        assert client.auto_start is False

    @patch("jota.ui.client.socket.socket")
    def test_client_send_state(self, mock_socket_cls, tmp_path):
        sock_file = tmp_path / "test_orb.sock"
        sock_file.touch()

        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock

        client = OrbClient(socket_path=sock_file, auto_start=False)
        client.set_state("listening", 0.5)

        mock_sock.sendall.assert_called_once()
        sent_data = mock_sock.sendall.call_args[0][0].decode("utf-8")
        assert "STATE listening 0.500" in sent_data

    @patch("jota.ui.client.socket.socket")
    def test_client_send_level(self, mock_socket_cls, tmp_path):
        sock_file = tmp_path / "test_orb.sock"
        sock_file.touch()

        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock

        client = OrbClient(socket_path=sock_file, auto_start=False)
        client.set_level(0.75)

        mock_sock.sendall.assert_called_once()
        sent_data = mock_sock.sendall.call_args[0][0].decode("utf-8")
        assert "LEVEL 0.750" in sent_data

    @patch("jota.ui.client.socket.socket")
    def test_client_quit(self, mock_socket_cls, tmp_path):
        sock_file = tmp_path / "test_orb.sock"
        sock_file.touch()

        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock

        client = OrbClient(socket_path=sock_file, auto_start=False)
        client.quit()

        mock_sock.sendall.assert_called_once()
        sent_data = mock_sock.sendall.call_args[0][0].decode("utf-8")
        assert "QUIT" in sent_data


class TestOrbWindowLogic:
    """Verifica la logica interna de estados del orbe."""

    def test_orb_window_states(self):
        try:
            import sys
            for p in ["/usr/lib/python3.14/site-packages", "/usr/lib64/python3.14/site-packages"]:
                if p not in sys.path:
                    sys.path.append(p)

            import gi
            gi.require_version("Gdk", "3.0")
            gi.require_version("Gtk", "3.0")
            gi.require_version("GtkLayerShell", "0.1")
            from jota.ui.orb import JotaOrbWindow
        except Exception:
            pytest.skip("GtkLayerShell no disponible en este entorno de prueba")

        win = JotaOrbWindow(size=120, corner="bottom_right")
        assert win.state == "idle"
        assert win.target_alpha == 0.0

        win.set_state("listening", 0.3)
        assert win.state == "listening"
        assert win.target_alpha == 1.0
        assert win.voice_level == 0.3

        win.set_state("thinking")
        assert win.state == "thinking"
        assert win.target_alpha == 1.0

        win.set_state("speaking")
        assert win.state == "speaking"
        assert win.target_alpha == 1.0

        win.set_state("idle")
        assert win.state == "idle"
        assert win.target_alpha == 0.0

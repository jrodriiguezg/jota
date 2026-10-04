"""
Cliente IPC para comunicar Jota con el orbe visual flotante en Wayland.
Permite cambiar el estado (listening, thinking, speaking, idle) y modular
el nivel de entrada de audio sin bloquear el hilo de ejecucion principal.
"""

import logging
import socket
import subprocess
import sys
import time
from pathlib import Path

from jota.config import ORB_ENABLED, ORB_SOCKET_PATH

logger = logging.getLogger(__name__)


class OrbClient:
    """Gestiona la conexion y envio de comandos al proceso del orbe visual."""

    def __init__(self, socket_path: Path = ORB_SOCKET_PATH, auto_start: bool = True):
        self.socket_path = socket_path
        self.auto_start = auto_start
        self._proc: subprocess.Popen | None = None
        self._sock: socket.socket | None = None

    def start(self) -> bool:
        """Asegura que el proceso del orbe este en ejecucion si esta habilitado."""
        if not ORB_ENABLED:
            return False

        if self._is_server_listening():
            return True

        if not self.auto_start:
            return False

        return self._spawn_orb_process()

    def _is_server_listening(self) -> bool:
        """Comprueba si el socket del orbe esta respondiendo."""
        if not self.socket_path.exists():
            return False
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                s.connect(str(self.socket_path))
                return True
        except Exception:
            return False

    def _spawn_orb_process(self) -> bool:
        """Lanza el orbe en un subproceso independiente."""
        logger.info("Iniciando proceso del orbe visual de Jota...")
        try:
            import os
            python_bin = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else sys.executable
            env = dict(os.environ)
            project_root = str(Path(__file__).resolve().parent.parent.parent)
            curr_pp = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = f"{project_root}:{curr_pp}" if curr_pp else project_root

            log_path = Path("/tmp/jota_orb.log")
            log_file = open(log_path, "a")
            self._proc = subprocess.Popen(
                [python_bin, "-m", "jota.ui.orb"],
                env=env,
                stdout=log_file,
                stderr=log_file,
                start_new_session=True,
            )

            # Esperar a que el socket este listo (hasta 2.5 segundos)
            for _ in range(50):
                time.sleep(0.05)
                if self._is_server_listening():
                    logger.info("Orbe visual conectado y listo.")
                    return True

            logger.warning("El socket del orbe no estuvo listo a tiempo. Revisa /tmp/jota_orb.log")
            return False
        except Exception as e:
            logger.error("No se pudo iniciar el orbe visual: %s", e)
            return False

    def set_state(self, state: str, level: float = 0.0) -> None:
        """Envia un cambio de estado al orbe (listening, thinking, speaking, idle)."""
        if not ORB_ENABLED:
            return
        self._send_command(f"STATE {state} {level:.3f}\n")

    def set_level(self, level: float) -> None:
        """Actualiza el nivel de modulacion de voz (0.0 a 1.0)."""
        if not ORB_ENABLED:
            return
        self._send_command(f"LEVEL {level:.3f}\n")

    def quit(self) -> None:
        """Solicita el cierre del orbe visual."""
        self._send_command("QUIT\n")
        self.close()

    def close(self) -> None:
        """Cierra el socket local."""
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _send_command(self, cmd: str) -> None:
        """Envia el comando crudo por el socket Unix con reconexion automatica."""
        # Intentar reutilizar o abrir socket
        for attempt in range(2):
            try:
                if self._sock is None:
                    if not self.socket_path.exists():
                        if attempt == 0 and self.auto_start:
                            self.start()
                        else:
                            return

                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.settimeout(0.3)
                    s.connect(str(self.socket_path))
                    self._sock = s

                self._sock.sendall(cmd.encode("utf-8"))
                return
            except Exception:
                self.close()
                if attempt == 0 and self.auto_start:
                    self.start()

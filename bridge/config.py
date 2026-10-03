"""
Configuracion del servidor Jota Bridge.
Define parametros de red, autenticacion y politicas de seguridad para archivos.
"""

import os
from pathlib import Path

# ── Red y Servidor ───────────────────────────────────────────────────────────
# Por defecto escucha en todas las interfaces de red del host (accesible por Tailscale).
BRIDGE_HOST: str = os.getenv("JOTA_BRIDGE_HOST", "0.0.0.0")
BRIDGE_PORT: int = int(os.getenv("JOTA_BRIDGE_PORT", "8765"))

# Clave secreta precompartida para autenticar solicitudes HTTP y WebSocket.
BRIDGE_API_KEY: str = os.getenv("JOTA_BRIDGE_API_KEY", "jota-secret-tailscale-key")

# Directorio temporal para almacenar audios recibidos y generados
BRIDGE_TEMP_DIR: Path = Path(os.getenv("JOTA_BRIDGE_TEMP_DIR", "/tmp/jota_bridge"))
BRIDGE_TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ── Politica de Seguridad de Archivos ─────────────────────────────────────────
# Rutas raiz autorizadas para descarga de archivos desde el movil
HOME_PATH = Path.home().resolve()
ALLOWED_ROOT_PATHS: list[Path] = [
    HOME_PATH,
    Path("/tmp").resolve(),
]

# Subrutas o patrones prohibidos explicitamente dentro del sistema de archivos
FORBIDDEN_PATH_PARTS: list[str] = [
    ".ssh",
    ".gnupg",
    ".pki",
    ".vault",
    ".env",
    "id_rsa",
    "id_ed25519",
    "private_key",
    "/etc/shadow",
    "/etc/sudoers",
]

# Tamano maximo de descarga de archivo permitido (100 MB)
MAX_FILE_DOWNLOAD_BYTES: int = 100 * 1024 * 1024

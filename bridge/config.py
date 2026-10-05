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
    ".bash_history",
    ".zsh_history",
    ".bashrc",
    ".zshrc",
    ".netrc",
    ".git-credentials",
    ".aws",
    ".docker",
    "credentials.json",
    ".config/gh",
]

# Tamano maximo de descarga y subida de archivos permitido (100 MB)
MAX_FILE_DOWNLOAD_BYTES: int = 100 * 1024 * 1024
MAX_FILE_UPLOAD_BYTES: int = 100 * 1024 * 1024

# Tiempo de vida de audios temporales en cache antes de eliminacion automatica (15 minutos)
AUDIO_CACHE_TTL_SECONDS: int = 900

# Parametros de proteccion contra fuerza bruta / rate limiting
AUTH_RATE_LIMIT_MAX_FAILURES: int = 10
AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 60

# Habilitar anuncio automatico mDNS / ZeroConf en la red local
ENABLE_MDNS_DISCOVERY: bool = os.getenv("JOTA_BRIDGE_MDNS", "true").lower() in ("true", "1", "yes")

# Auto-configurar redireccion inversa ADB para conexion por cable USB si hay dispositivo
ENABLE_AUTO_ADB_REVERSE: bool = os.getenv(
    "JOTA_BRIDGE_AUTO_ADB", "true"
).lower() in ("true", "1", "yes")


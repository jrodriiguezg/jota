#!/usr/bin/env bash
# ==============================================================================
# Jota Satelite - Instalador Automatizado (satelite-0.1)
# Configura el cliente nativo en modo interactivo (desktop) o monitorizacion (headless).
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

SERVER_IP=""
SERVER_PORT="8765"
SERVER_TOKEN=""
MODE="desktop"
NODE_NAME="$(hostname 2>/dev/null || echo "jota-satellite")"
UNATTENDED=false

show_help() {
    cat <<EOF
Uso: $0 [OPCIONES]

Instalador automatizado para Jota Satelite.

Opciones:
  --server-ip <IP_O_HOST>       Direccion IP o dominio de Jota Hub
  --server-port, --port <PUERTO> Puerto del servidor Hub (por defecto: 8765)
  --server-token <TOKEN>        Token secreto del cluster (X-Jota-Token)
  --mode <desktop|headless>     Perfil de instalacion (por defecto: desktop)
  --name <NOMBRE_NODO>          Nombre de este equipo en el cluster (por defecto: hostname)
  --unattended                  Ejecucion no interactiva (requiere IP y Token)
  -h, --help                    Muestra esta ayuda

Ejemplos:
  $0 --server-ip 192.168.1.100 --server-token secreto123 --mode desktop
  $0 --server-ip 100.85.176.113 --server-token secreto123 --mode headless --unattended
EOF
    exit 0
}

# 1. Parseo de argumentos de linea de comandos
while [[ $# -gt 0 ]]; do
    case "$1" in
        --server-ip)
            SERVER_IP="$2"
            shift 2
            ;;
        --server-ip=*)
            SERVER_IP="${1#*=}"
            shift 1
            ;;
        --server-port|--port)
            SERVER_PORT="$2"
            shift 2
            ;;
        --server-port=*|--port=*)
            SERVER_PORT="${1#*=}"
            shift 1
            ;;
        --server-token)
            SERVER_TOKEN="$2"
            shift 2
            ;;
        --server-token=*)
            SERVER_TOKEN="${1#*=}"
            shift 1
            ;;
        --mode)
            MODE="$2"
            shift 2
            ;;
        --mode=*)
            MODE="${1#*=}"
            shift 1
            ;;
        --name)
            NODE_NAME="$2"
            shift 2
            ;;
        --name=*)
            NODE_NAME="${1#*=}"
            shift 1
            ;;
        --unattended)
            UNATTENDED=true
            shift 1
            ;;
        -h|--help)
            show_help
            ;;
        *)
            echo "Parametro no reconocido: $1"
            show_help
            ;;
    esac
done

echo "=================================================="
echo "  Instalador Automatizado de Jota Satelite        "
echo "  Perfil: ${MODE} | Nodo: ${NODE_NAME}           "
echo "=================================================="

# 2. Descubrimiento automatico mDNS / Fallback interactivo
if [[ -z "${SERVER_IP}" ]]; then
    DISCOVERED_IP=""
    echo "Buscando Jota Hub en la red local via mDNS (ZeroConf)..."
    if command -v avahi-browse >/dev/null 2>&1; then
        DISCOVERED_IP=$(avahi-browse -rt _jota-hub._tcp 2>/dev/null | grep -Eo 'address = \[[0-9.]+\]' | grep -Eo '[0-9.]+' | head -n 1 || true)
    fi

    if [[ -n "${DISCOVERED_IP}" ]]; then
        echo "Hub detectado automaticamente en: ${DISCOVERED_IP}"
        SERVER_IP="${DISCOVERED_IP}"
    elif [[ "${UNATTENDED}" == "true" ]]; then
        echo "Error: Debes especificar --server-ip en modo desatendido cuando mDNS no localiza un Hub." >&2
        exit 1
    else
        read -r -p "Introduce la IP o dominio de Jota Hub [127.0.0.1]: " INPUT_IP
        SERVER_IP="${INPUT_IP:-127.0.0.1}"
    fi
fi

if [[ -z "${SERVER_TOKEN}" ]]; then
    if [[ "${UNATTENDED}" == "true" ]]; then
        echo "Error: Debes especificar --server-token en modo desatendido." >&2
        exit 1
    else
        read -r -s -p "Introduce el token secreto del cluster (X-Jota-Token): " SERVER_TOKEN
        echo ""
    fi
fi

if [[ -z "${SERVER_TOKEN}" ]]; then
    echo "Error: El token no puede estar vacio." >&2
    exit 1
fi

# 3. Validacion de conexion con el Hub
echo "Verificando conectividad con http://${SERVER_IP}:${SERVER_PORT}/health..."
if curl -fsSL -m 5 "http://${SERVER_IP}:${SERVER_PORT}/health" >/dev/null 2>&1; then
    echo "Conexion con Jota Hub confirmada exitosamente."
else
    echo "Aviso: No se pudo contactar con http://${SERVER_IP}:${SERVER_PORT}/health."
    echo "Verifica que el Hub este levantado y que la IP/puerto sean correctos."
    if [[ "${UNATTENDED}" != "true" ]]; then
        read -r -p "Deseas continuar con la instalacion de todas formas? (s/N): " CONT
        if [[ "${CONT}" != "s" && "${CONT}" != "S" ]]; then
            echo "Instalacion cancelada por el usuario."
            exit 1
        fi
    fi
fi

# 4. Preparar entorno Python virtual (.venv)
echo "Configurando entorno virtual de Python..."
if [[ ! -d ".venv" ]]; then
    python3 -m venv .venv
fi

VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python"
VENV_PIP="${SCRIPT_DIR}/.venv/bin/pip"

"${VENV_PIP}" install --upgrade pip setuptools wheel --quiet
"${VENV_PIP}" install --quiet cryptography pyyaml httpx psutil

if [[ "${MODE}" == "desktop" ]]; then
    echo "Instalando dependencias de escritorio y audio..."
    "${VENV_PIP}" install -e . --quiet || true
else
    echo "Modo Headless: instalando dependencias ligeras de telemetria..."
    "${VENV_PIP}" install -e . --no-deps --quiet || true
fi

# 5. Generacion de configuracion local protegida
CONFIG_DIR="${HOME}/.config/jota"
CONFIG_FILE="${CONFIG_DIR}/satelite.yaml"
mkdir -p "${CONFIG_DIR}"
chmod 700 "${CONFIG_DIR}"

cat <<EOF > "${CONFIG_FILE}"
node:
  name: "${NODE_NAME}"
  mode: "${MODE}"

hub:
  host: "${SERVER_IP}"
  port: ${SERVER_PORT}
  token: "${SERVER_TOKEN}"
  heartbeat_interval_sec: 15.0

telemetry:
  interval_sec: 30.0
  systemd_services:
    - "sshd"
    - "docker"
    - "podman"
EOF

chmod 600 "${CONFIG_FILE}"
echo "Configuracion guardada en: ${CONFIG_FILE} (permisos 0600)"

# 6. Generacion e instalacion del servicio systemd
USER_SYSTEMD_DIR="${HOME}/.config/systemd/user"
mkdir -p "${USER_SYSTEMD_DIR}"
SERVICE_FILE="${USER_SYSTEMD_DIR}/jota-satelite.service"

WANTED_TARGET="default.target"
AFTER_TARGET="network.target"

if [[ "${MODE}" == "desktop" ]]; then
    WANTED_TARGET="graphical-session.target default.target"
    AFTER_TARGET="network.target graphical-session.target pipewire.service"
fi

cat <<EOF > "${SERVICE_FILE}"
[Unit]
Description=Jota Satelite (${MODE})
After=${AFTER_TARGET}
Wants=network.target

[Service]
Type=simple
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${VENV_PYTHON} -m jota.satellite --mode ${MODE}
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=${WANTED_TARGET}
EOF

echo "Servicio systemd creado en: ${SERVICE_FILE}"
systemctl --user daemon-reload || true
systemctl --user enable jota-satelite.service || true

# 7. Diagnostico final de identidad
NODE_ID=$("${VENV_PYTHON}" -c "from jota.identity import get_node_id; print(get_node_id())" 2>/dev/null || echo "desconocido")

echo "=================================================="
echo "  Instalacion de Jota Satelite Completada         "
echo "  Node ID:     ${NODE_ID}                         "
echo "  Modo:        ${MODE}                            "
echo "  Hub:         http://${SERVER_IP}:${SERVER_PORT} "
echo "=================================================="
echo "Comandos utiles:"
echo "  Iniciar ahora:    systemctl --user start jota-satelite.service"
echo "  Ver estado:       systemctl --user status jota-satelite.service"
echo "  Ver registros:    journalctl --user -u jota-satelite.service -f"
echo "=================================================="

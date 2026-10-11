#!/usr/bin/env bash
# =============================================================================
#  install.sh - Instalador Automatizado Unificado de Jota
#
#  Soporta los 3 modos de operacion:
#    1) standalone : Solo PC (offline, sin red ni servidor, tecla Copilot)
#    2) bridge     : PC + Movil (PC como servidor local para Android JotaLink)
#    3) hub        : Servidor Homelab 24/7 (Docker en servidor para movil y homelab)
#
#  Uso:
#    bash install.sh                  (Modo interactivo)
#    bash install.sh --mode=standalone
#    bash install.sh --mode=bridge
#    bash install.sh --mode=hub
# =============================================================================

set -euo pipefail

# Paleta de colores para terminal
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}  [OK]${NC} $*"; }
info() { echo -e "${BLUE}  -->${NC} $*"; }
warn() { echo -e "${YELLOW}  [!]${NC} $*"; }
err()  { echo -e "${RED}  [X]${NC} $*" >&2; }
step() { echo -e "\n${BOLD}${BLUE}[$1]${NC} ${BOLD}$2${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MODELS_DIR="$HOME/.local/share/jota/models"
WHISPER_BIN="$HOME/.local/bin/whisper-cli"
PIPER_BIN="$HOME/.local/bin/piper"
WHISPER_BUILD_DIR="/tmp/jota-whisper-build"

WHISPER_MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin"
PIPER_MODEL_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/sharvard/medium"
PIPER_MODEL_NAME="es_ES-sharvard-medium"
QWEN_MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
QWEN_MODEL_NAME="qwen2.5-1.5b-instruct-q4_k_m.gguf"

print_banner() {
    echo -e "\n${BOLD}====================================================${NC}"
    echo -e "${BOLD}  Jota - Instalador Automatizado Unificado${NC}"
    echo -e "${BOLD}====================================================${NC}"
}

check_system_packages() {
    step "1/6" "Dependencias del sistema operativo"
    if command -v dnf &>/dev/null; then
        PKGS=(python3-devel portaudio-devel libsndfile-devel cmake make gcc-c++ git curl jq)
        MISSING=()
        for pkg in "${PKGS[@]}"; do
            if ! rpm -q "$pkg" &>/dev/null; then
                MISSING+=("$pkg")
            fi
        done
        if [[ ${#MISSING[@]} -eq 0 ]]; then
            ok "Todos los paquetes del sistema estan instalados."
        else
            info "Instalando paquetes: ${MISSING[*]}"
            sudo dnf install -y "${MISSING[@]}"
            ok "Paquetes instalados."
        fi
    elif command -v apt-get &>/dev/null; then
        sudo apt-get update
        sudo apt-get install -y python3-dev libasound2-dev libportaudio2 portaudio19-dev \
            libsndfile1-dev cmake make g++ git curl jq ffmpeg
        ok "Paquetes apt instalados."
    else
        warn "Gestor de paquetes no reconocido (no es dnf ni apt). Asegurate de tener cmake, g++, portaudio y python3-dev."
    fi
}

setup_input_group() {
    step "2/6" "Permisos de hardware (tecla Copilot / evdev)"
    if groups | grep -q '\binput\b'; then
        ok "Usuario ya pertenece al grupo 'input'."
    else
        info "Anadiendo usuario '$USER' al grupo 'input'..."
        sudo usermod -aG input "$USER"
        warn "Debes cerrar sesion y volver a entrar para que el grupo 'input' surta efecto en evdev."
    fi
}

build_whisper_cli() {
    step "3/6" "Motor STT whisper.cpp (whisper-cli)"
    if [[ -x "$WHISPER_BIN" ]]; then
        ok "whisper-cli ya esta presente en $WHISPER_BIN"
    else
        info "Compilando whisper-cli desde fuente..."
        rm -rf "$WHISPER_BUILD_DIR"
        git clone --depth 1 https://github.com/ggerganov/whisper.cpp "$WHISPER_BUILD_DIR"
        mkdir -p "$WHISPER_BUILD_DIR/build"
        cmake -B "$WHISPER_BUILD_DIR/build" -S "$WHISPER_BUILD_DIR" \
            -DCMAKE_BUILD_TYPE=Release \
            -DWHISPER_BUILD_TESTS=OFF \
            -DWHISPER_BUILD_EXAMPLES=ON
        cmake --build "$WHISPER_BUILD_DIR/build" --config Release -j "$(nproc)" --target whisper-cli
        mkdir -p "$HOME/.local/bin"
        cp "$WHISPER_BUILD_DIR/build/bin/whisper-cli" "$WHISPER_BIN"
        chmod +x "$WHISPER_BIN"
        rm -rf "$WHISPER_BUILD_DIR"
        ok "whisper-cli instalado en $WHISPER_BIN"
    fi
}

install_piper_tts() {
    step "4/6" "Motor TTS piper-tts"
    if [[ -x "$PIPER_BIN" ]]; then
        ok "piper ya esta presente en $PIPER_BIN"
    else
        info "Descargando binario oficial de piper..."
        local tmp_piper="/tmp/piper_download.tar.gz"
        curl -sSL "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz" -o "$tmp_piper"
        tar -xzf "$tmp_piper" -C "/tmp"
        mkdir -p "$HOME/.local/bin" "$HOME/.local/lib/piper"
        cp -r /tmp/piper/* "$HOME/.local/lib/piper/"
        ln -sf "$HOME/.local/lib/piper/piper" "$PIPER_BIN"
        chmod +x "$PIPER_BIN"
        rm -f "$tmp_piper"
        ok "piper instalado en $PIPER_BIN"
    fi
}

download_models() {
    step "5/6" "Descarga de modelos IA locales"
    mkdir -p "$MODELS_DIR/whisper" "$MODELS_DIR/piper" "$MODELS_DIR/qwen"

    # 1. Whisper small
    if [[ -f "$MODELS_DIR/whisper/ggml-small.bin" ]]; then
        ok "Modelo whisper ggml-small.bin ya descargado."
    else
        info "Descargando modelo Whisper (ggml-small.bin ~466MB)..."
        curl -L --progress-bar "$WHISPER_MODEL_URL" -o "$MODELS_DIR/whisper/ggml-small.bin"
        ok "Whisper small descargado."
    fi

    # 2. Piper voz espanol
    if [[ -f "$MODELS_DIR/piper/${PIPER_MODEL_NAME}.onnx" ]]; then
        ok "Modelo piper voz ya descargado."
    else
        info "Descargando modelo Piper es_ES-sharvard-medium (~50MB)..."
        curl -L --progress-bar "${PIPER_MODEL_BASE}/${PIPER_MODEL_NAME}.onnx" -o "$MODELS_DIR/piper/${PIPER_MODEL_NAME}.onnx"
        curl -L --progress-bar "${PIPER_MODEL_BASE}/${PIPER_MODEL_NAME}.onnx.json" -o "$MODELS_DIR/piper/${PIPER_MODEL_NAME}.onnx.json"
        ok "Piper modelo descargado."
    fi

    # 3. Qwen 2.5 1.5B
    if [[ -f "$MODELS_DIR/qwen/$QWEN_MODEL_NAME" ]]; then
        ok "Modelo LLM $QWEN_MODEL_NAME ya descargado."
    else
        info "Descargando modelo LLM ($QWEN_MODEL_NAME ~1.1GB)..."
        curl -L --progress-bar "$QWEN_MODEL_URL" -o "$MODELS_DIR/qwen/$QWEN_MODEL_NAME"
        ok "Modelo LLM descargado."
    fi
}

setup_python_venv() {
    local with_bridge="${1:-false}"
    step "6/6" "Entorno virtual Python y dependencias"
    if [[ ! -d ".venv" ]]; then
        info "Creando virtualenv en .venv..."
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    pip install --upgrade pip setuptools wheel

    info "Instalando paquetes basicos..."
    pip install -e .

    if [[ "$with_bridge" == "true" ]]; then
        info "Instalando dependencias adicionales del Bridge..."
        pip install fastapi "uvicorn[standard]" httpx python-multipart zeroconf requests faster-whisper
    fi
    ok "Virtualenv configurado con exito."
}

configure_systemd() {
    local exec_cmd="$1"
    local desc="$2"
    info "Configurando servicio systemd user ($desc)..."
    mkdir -p "$HOME/.config/systemd/user"
    cat > "$HOME/.config/systemd/user/jota.service" <<EOF
[Unit]
Description=$desc
Documentation=https://github.com/jrodriiguezg/jota
After=network-online.target pipewire.service wireplumber.service
Wants=network-online.target pipewire.service wireplumber.service
PartOf=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=$exec_cmd
Restart=always
RestartSec=3
KillMode=control-group
Environment=PYTHONUNBUFFERED=1
Environment=PATH=$SCRIPT_DIR/.venv/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
PassEnvironment=WAYLAND_DISPLAY DISPLAY XDG_CURRENT_DESKTOP XDG_RUNTIME_DIR

StandardOutput=journal
StandardError=journal
SyslogIdentifier=jota

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable jota.service
    loginctl enable-linger "$USER" || true
    systemctl --user restart jota.service
    ok "Servicio jota.service activado y en ejecucion."
}

install_standalone() {
    info "Iniciando instalacion: Modo 1 (Solo PC / Standalone)"
    check_system_packages
    setup_input_group
    build_whisper_cli
    install_piper_tts
    download_models
    setup_python_venv "false"
    configure_systemd "$SCRIPT_DIR/.venv/bin/jota" "Jota - Asistente de Voz Local (Solo PC)"
    echo -e "\n${BOLD}${GREEN}====================================================${NC}"
    echo -e "${BOLD}${GREEN}  Instalacion Standalone completada con exito.${NC}"
    echo -e "${BOLD}${GREEN}====================================================${NC}"
    echo -e "Prueba pulsar la tecla Copilot o ejecuta: ${BOLD}.venv/bin/jota${NC}"
}

install_bridge() {
    info "Iniciando instalacion: Modo 2 (PC + Movil / Bridge)"
    check_system_packages
    setup_input_group
    build_whisper_cli
    install_piper_tts
    download_models
    setup_python_venv "true"
    configure_systemd "$SCRIPT_DIR/.venv/bin/jota-bridge" "Jota - Asistente de Voz y Bridge Multi-Dispositivo"
    echo -e "\n${BOLD}${GREEN}====================================================${NC}"
    echo -e "${BOLD}${GREEN}  Instalacion Bridge completada con exito.${NC}"
    echo -e "${BOLD}${GREEN}====================================================${NC}"
    echo -e "El servidor Bridge escucha en: ${BOLD}http://0.0.0.0:8765${NC}"
    echo -e "Conecta la app JotaLink en Android usando la IP local o de Tailscale."
}

install_hub() {
    info "Iniciando instalacion: Modo 3 (Servidor Homelab / Docker Hub)"
    if ! command -v docker &>/dev/null; then
        err "Docker no esta instalado. Instala Docker y Docker Compose en tu servidor."
        exit 1
    fi

    local target_dir="${DOCKER_TARGET_DIR:-$SCRIPT_DIR/docker/jota-hub}"
    mkdir -p "$target_dir/data" "$target_dir/models/qwen"

    if [[ -f "$MODELS_DIR/qwen/$QWEN_MODEL_NAME" ]]; then
        info "Copiando modelo Qwen local a $target_dir/models/qwen/..."
        cp "$MODELS_DIR/qwen/$QWEN_MODEL_NAME" "$target_dir/models/qwen/"
    else
        info "Descargando modelo Qwen para el Hub..."
        curl -L --progress-bar "$QWEN_MODEL_URL" -o "$target_dir/models/qwen/$QWEN_MODEL_NAME"
    fi

    info "Compilando y arrancando contenedor Docker Jota Hub..."
    cd "$target_dir"
    docker compose up -d --build
    ok "Contenedor jota-hub levantado en el puerto 8765."
    echo -e "\n${BOLD}${GREEN}====================================================${NC}"
    echo -e "${BOLD}${GREEN}  Jota Hub instalado y en ejecucion.${NC}"
    echo -e "${BOLD}${GREEN}====================================================${NC}"
    echo -e "Verifica el estado con: ${BOLD}curl -s http://localhost:8765/api/v1/pc/status | jq .${NC}"
}

# ── Parseo de argumentos ──────────────────────────────────────────────────────
MODE=""
for arg in "$@"; do
    case "$arg" in
        --mode=standalone) MODE="standalone" ;;
        --mode=bridge)     MODE="bridge" ;;
        --mode=hub)        MODE="hub" ;;
        --help|-h)
            echo "Uso: bash install.sh [--mode=standalone|bridge|hub]"
            exit 0
            ;;
    esac
done

print_banner

if [[ -z "$MODE" ]]; then
    echo -e "Selecciona el modo de instalacion:"
    echo -e "  ${BOLD}1) Solo PC (Standalone)${NC}   - 100% offline en tu PC, sin red ni servidor."
    echo -e "  ${BOLD}2) PC + Movil (Bridge)${NC}    - Tu PC actua de puente para la app Android."
    echo -e "  ${BOLD}3) Servidor Homelab (Hub)${NC} - Contenedor Docker 24/7 en servidor homelab."
    echo ""
    read -rp "Opcion [1-3]: " opt
    case "$opt" in
        1) MODE="standalone" ;;
        2) MODE="bridge" ;;
        3) MODE="hub" ;;
        *) err "Opcion no valida. Abortando."; exit 1 ;;
    esac
fi

case "$MODE" in
    standalone) install_standalone ;;
    bridge)     install_bridge ;;
    hub)        install_hub ;;
    *)          err "Modo desconocido: $MODE"; exit 1 ;;
esac

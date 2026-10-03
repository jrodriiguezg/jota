#!/usr/bin/env bash
# =============================================================================
#  setup.sh — Instalación automática de Jota (Fase 1)
#  Target: Fedora Linux
#  Uso:    bash setup.sh
# =============================================================================

set -euo pipefail

# ── Colores ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}  [OK]${NC} $*"; }
info() { echo -e "${BLUE}  -->${NC} $*"; }
warn() { echo -e "${YELLOW}  [!]${NC} $*"; }
err()  { echo -e "${RED}  [X]${NC} $*" >&2; }
step() { echo -e "\n${BOLD}${BLUE}[$1]${NC} ${BOLD}$2${NC}"; }

# ── Config ────────────────────────────────────────────────────────────────────
MODELS_DIR="$HOME/.local/share/jota/models"
WHISPER_BIN="/usr/local/bin/whisper-cli"
PIPER_BIN="$HOME/.local/bin/piper"
WHISPER_BUILD_DIR="/tmp/jota-whisper-build"
PIPER_VERSION="2023.11.14-2"

WHISPER_MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin"
PIPER_MODEL_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/sharvard/medium"
PIPER_MODEL_NAME="es_ES-sharvard-medium"
QWEN_MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"
QWEN_MODEL_NAME="qwen2.5-0.5b-instruct-q4_k_m.gguf"

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}====================================================${NC}"
echo -e "${BOLD}  Jota -- Setup automatico (Fase 1)${NC}"
echo -e "${BOLD}====================================================${NC}"
echo -e "  Modelos -> ${MODELS_DIR}"
echo ""

# ── Detección de distro ───────────────────────────────────────────────────────
if ! command -v dnf &>/dev/null; then
    err "Este script está pensado para Fedora (dnf). Adapta la sección de paquetes si usas otra distro."
    exit 1
fi

# ── Helper: ya instalado? ─────────────────────────────────────────────────────
already() { ok "$1 ya está instalado, saltando."; }

# =============================================================================
step "1/8" "Grupo 'input' (necesario para tecla Copilot sin sudo)"
# =============================================================================
if groups | grep -q '\binput\b'; then
    already "Grupo input"
else
    if sudo -n true 2>/dev/null; then
        info "Añadiendo $USER al grupo input..."
        sudo usermod -aG input "$USER"
        warn "Necesitarás re-loguearte para que el grupo surta efecto."
    else
        warn "Tu usuario ($USER) aún no está en el grupo 'input'."
        warn "Para activarlo, ejecuta en tu terminal: sudo usermod -aG input $USER"
    fi
fi

# =============================================================================
step "2/8" "Dependencias del sistema (Fedora)"
# =============================================================================
PKGS=(python3-devel portaudio-devel libsndfile-devel cmake make gcc-c++ git curl)
MISSING=()
for pkg in "${PKGS[@]}"; do
    if ! rpm -q "$pkg" &>/dev/null; then
        MISSING+=("$pkg")
    fi
done

if [[ ${#MISSING[@]} -eq 0 ]]; then
    already "Todos los paquetes del sistema"
else
    info "Instalando: ${MISSING[*]}"
    if sudo -n true 2>/dev/null || [ -t 0 ]; then
        sudo dnf install -y "${MISSING[@]}"
        ok "Paquetes instalados."
    else
        err "Se requiere contraseña de sudo para instalar: ${MISSING[*]}"
        echo -e "    Ejecuta en tu terminal: ${BOLD}sudo dnf install -y ${MISSING[*]}${NC}"
        exit 1
    fi
fi

# =============================================================================
step "3/8" "whisper.cpp -> whisper-cli"
# =============================================================================
if [[ -x "$WHISPER_BIN" ]]; then
    already "whisper-cli ($WHISPER_BIN)"
else
    info "Clonando whisper.cpp..."
    rm -rf "$WHISPER_BUILD_DIR"
    git clone --depth 1 https://github.com/ggerganov/whisper.cpp "$WHISPER_BUILD_DIR"

    info "Compilando (esto puede tardar unos minutos)..."
    cmake -B "$WHISPER_BUILD_DIR/build" \
          -S "$WHISPER_BUILD_DIR" \
          -DCMAKE_BUILD_TYPE=Release \
          -DWHISPER_BUILD_TESTS=OFF \
          -DWHISPER_BUILD_EXAMPLES=ON \
          2>&1 | tail -3

    cmake --build "$WHISPER_BUILD_DIR/build" \
          --config Release \
          --target whisper-cli \
          -j"$(nproc)" \
          2>&1 | tail -5

    sudo install -m 755 "$WHISPER_BUILD_DIR/build/bin/whisper-cli" "$WHISPER_BIN"
    ok "whisper-cli instalado en $WHISPER_BIN"
    rm -rf "$WHISPER_BUILD_DIR"
fi

# =============================================================================
step "4/8" "Modelo Whisper (ggml-small.bin, ~244 MB)"
# =============================================================================
mkdir -p "$MODELS_DIR/whisper"
WHISPER_MODEL="$MODELS_DIR/whisper/ggml-small.bin"

if [[ -f "$WHISPER_MODEL" ]]; then
    already "ggml-small.bin"
else
    info "Descargando modelo Whisper small (español)..."
    curl -L "$WHISPER_MODEL_URL" -o "$WHISPER_MODEL" --progress-bar
    ok "Modelo guardado en $WHISPER_MODEL"
fi

# =============================================================================
step "5/8" "piper-tts"
# =============================================================================
if command -v piper &>/dev/null || [[ -x "$PIPER_BIN" ]]; then
    already "piper ($(command -v piper || echo "$PIPER_BIN"))"
else
    ARCH="$(uname -m)"
    case "$ARCH" in
        x86_64)  PIPER_ARCH="x86_64" ;;
        aarch64) PIPER_ARCH="aarch64" ;;
        *)
            err "Arquitectura $ARCH no soportada por los binarios de piper."
            err "Compílalo manualmente: https://github.com/rhasspy/piper"
            exit 1
            ;;
    esac

    PIPER_INSTALL_DIR="$HOME/.local/share/jota/piper"
    PIPER_TAR="/tmp/piper_${PIPER_ARCH}.tar.gz"
    info "Descargando piper-tts (${PIPER_ARCH})..."
    curl -L "https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_${PIPER_ARCH}.tar.gz" \
         -o "$PIPER_TAR" --progress-bar

    info "Extrayendo en $PIPER_INSTALL_DIR..."
    mkdir -p "$HOME/.local/share/jota" "$HOME/.local/bin"
    rm -rf "$PIPER_INSTALL_DIR"
    tar -xzf "$PIPER_TAR" -C "$HOME/.local/share/jota/"
    ln -sf "$PIPER_INSTALL_DIR/piper" "$PIPER_BIN"
    rm -f "$PIPER_TAR"
    ok "piper instalado en $PIPER_BIN"
fi

# =============================================================================
step "6/8" "Modelo de voz Piper (español, ~60 MB)"
# =============================================================================
mkdir -p "$MODELS_DIR/piper"
PIPER_ONNX="$MODELS_DIR/piper/${PIPER_MODEL_NAME}.onnx"

if [[ -f "$PIPER_ONNX" ]]; then
    already "${PIPER_MODEL_NAME}.onnx"
else
    info "Descargando modelo de voz en español..."
    curl -L "${PIPER_MODEL_BASE}/${PIPER_MODEL_NAME}.onnx" \
         -o "$PIPER_ONNX" --progress-bar
    curl -L "${PIPER_MODEL_BASE}/${PIPER_MODEL_NAME}.onnx.json" \
         -o "${PIPER_ONNX}.json" --progress-bar
    ok "Modelo de voz guardado."
fi

# Smoke test de piper
info "Probando piper-tts..."
PIPER_CMD="$(command -v piper || echo "$PIPER_BIN")"
if echo "Hola, soy Jota." | "$PIPER_CMD" \
        --model "$PIPER_ONNX" \
        --output_file /tmp/jota-test.wav 2>/dev/null; then
    ok "piper funciona correctamente."
    rm -f /tmp/jota-test.wav
else
    warn "piper generó un error en el test. Comprueba la instalación manualmente."
fi

# =============================================================================
step "7/8" "Modelo LLM Qwen GGUF (~398 MB)"
# =============================================================================
mkdir -p "$MODELS_DIR/qwen"
QWEN_MODEL_FILE="$MODELS_DIR/qwen/$QWEN_MODEL_NAME"

if ls "$MODELS_DIR/qwen"/*.gguf &>/dev/null 2>&1; then
    already "Modelo Qwen GGUF ($(ls "$MODELS_DIR/qwen"/*.gguf | head -1))"
else
    info "Descargando modelo Qwen 2.5 0.5B Instruct GGUF (q4_k_m)..."
    curl -L "$QWEN_MODEL_URL" -o "$QWEN_MODEL_FILE" --progress-bar
    ok "Modelo Qwen guardado en $QWEN_MODEL_FILE"
fi

# =============================================================================
step "8/8" "Entorno Python y dependencias"
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    info "Creando entorno virtual..."
    python3 -m venv "$SCRIPT_DIR/.venv"
    ok "Entorno virtual creado en .venv/"
else
    already "Entorno virtual .venv"
fi

info "Instalando dependencias Python..."
"$SCRIPT_DIR/.venv/bin/pip" install --upgrade pip setuptools wheel -q
"$SCRIPT_DIR/.venv/bin/pip" install -e "$SCRIPT_DIR[dev]" -q
ok "Dependencias Python instaladas."

# Smoke test del LLM
info "Probando carga y respuesta del LLM..."
if "$SCRIPT_DIR/.venv/bin/python" -c "from jota import llm; llm.load_model(); resp = llm.ask('Di hola'); print('Respuesta LLM:', resp)" 2>/dev/null; then
    ok "LLM verificado correctamente."
else
    warn "No se pudo completar el test del LLM. Revisa que el modelo GGUF este presente."
fi

# =============================================================================
# Keycode de la tecla Copilot
# =============================================================================
echo ""
echo -e "${BOLD}${YELLOW}====================================================${NC}"
echo -e "${BOLD}${YELLOW}  [!] Configuracion de la tecla Copilot${NC}"
echo -e "${BOLD}${YELLOW}====================================================${NC}"
echo ""
echo "  Ejecuta esto para encontrar el scancode de tu tecla:"
echo "    source .venv/bin/activate"
echo "    python tools/find_copilot_key.py"
echo ""
echo "  Luego edita jota/config.py si difiere del valor por defecto:"
echo "    COPILOT_KEY_CODE = 0x???  # tu scancode"

# =============================================================================
# Resumen final
# =============================================================================
echo ""
echo -e "${BOLD}${GREEN}====================================================${NC}"
echo -e "${BOLD}${GREEN}  [OK] Setup completado al 100%${NC}"
echo -e "${BOLD}${GREEN}====================================================${NC}"
echo ""
echo "  Para iniciar el asistente Jota:"
echo ""
echo "    source .venv/bin/activate"
echo "    jota"
echo ""
if ! groups | grep -q '\binput\b'; then
    echo -e "  ${YELLOW}[!] Recuerda re-loguearte para activar el grupo 'input'${NC}"
    echo ""
fi

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

ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
info() { echo -e "${BLUE}  →${NC} $*"; }
warn() { echo -e "${YELLOW}  ⚠${NC} $*"; }
err()  { echo -e "${RED}  ✗${NC} $*" >&2; }
step() { echo -e "\n${BOLD}${BLUE}[$1]${NC} ${BOLD}$2${NC}"; }

# ── Config ────────────────────────────────────────────────────────────────────
MODELS_DIR="$HOME/.local/share/jota/models"
WHISPER_BIN="/usr/local/bin/whisper-cli"
PIPER_BIN="/usr/bin/piper"
WHISPER_BUILD_DIR="/tmp/jota-whisper-build"
PIPER_VERSION="2023.11.14-2"

WHISPER_MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin"
PIPER_MODEL_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/sharvard/medium"
PIPER_MODEL_NAME="es_ES-sharvard-medium"

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  🎙️  Jota — Setup automático (Fase 1)${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "  Modelos → ${MODELS_DIR}"
echo ""

# ── Detección de distro ───────────────────────────────────────────────────────
if ! command -v dnf &>/dev/null; then
    err "Este script está pensado para Fedora (dnf). Adapta la sección de paquetes si usas otra distro."
    exit 1
fi

# ── Helper: ya instalado? ─────────────────────────────────────────────────────
already() { ok "$1 ya está instalado, saltando."; }

# =============================================================================
step "1/7" "Grupo 'input' (necesario para tecla Copilot sin sudo)"
# =============================================================================
if groups | grep -q '\binput\b'; then
    already "Grupo input"
else
    info "Añadiendo $USER al grupo input..."
    sudo usermod -aG input "$USER"
    warn "Necesitarás re-loguearte para que el grupo surta efecto."
fi

# =============================================================================
step "2/7" "Dependencias del sistema (Fedora)"
# =============================================================================
PKGS=(portaudio-devel libsndfile-devel cmake make gcc-c++ git curl)
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
    sudo dnf install -y "${MISSING[@]}"
    ok "Paquetes instalados."
fi

# =============================================================================
step "3/7" "whisper.cpp → whisper-cli"
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
step "4/7" "Modelo Whisper (ggml-small.bin, ~244 MB)"
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
step "5/7" "piper-tts"
# =============================================================================
if [[ -x "$PIPER_BIN" ]]; then
    already "piper ($PIPER_BIN)"
else
    ARCH="$(uname -m)"
    case "$ARCH" in
        x86_64)  PIPER_ARCH="amd64" ;;
        aarch64) PIPER_ARCH="arm64" ;;
        *)
            err "Arquitectura $ARCH no soportada por los binarios de piper."
            err "Compílalo manualmente: https://github.com/rhasspy/piper"
            exit 1
            ;;
    esac

    PIPER_TAR="/tmp/piper_${PIPER_ARCH}.tar.gz"
    info "Descargando piper-tts (${PIPER_ARCH})..."
    curl -L "https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_${PIPER_ARCH}.tar.gz" \
         -o "$PIPER_TAR" --progress-bar

    info "Extrayendo..."
    tar -xzf "$PIPER_TAR" -C /tmp/
    sudo install -m 755 /tmp/piper/piper "$PIPER_BIN"
    # piper necesita libonnxruntime junto al binario
    sudo cp /tmp/piper/libonnxruntime*.so* /usr/lib/ 2>/dev/null || true
    sudo ldconfig
    rm -rf /tmp/piper "$PIPER_TAR"
    ok "piper instalado en $PIPER_BIN"
fi

# =============================================================================
step "6/7" "Modelo de voz Piper (español, ~60 MB)"
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
if echo "Hola, soy Jota." | piper \
        --model "$PIPER_ONNX" \
        --output_file /tmp/jota-test.wav 2>/dev/null; then
    ok "piper funciona correctamente."
    rm -f /tmp/jota-test.wav
else
    warn "piper generó un error en el test. Comprueba la instalación manualmente."
fi

# =============================================================================
step "7/7" "Entorno Python y dependencias"
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
"$SCRIPT_DIR/.venv/bin/pip" install --upgrade pip -q
"$SCRIPT_DIR/.venv/bin/pip" install -e "$SCRIPT_DIR[dev]" -q
ok "Dependencias Python instaladas."

# =============================================================================
# Modelo Qwen (no automatizable sin huggingface-cli o token)
# =============================================================================
echo ""
echo -e "${BOLD}${YELLOW}════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${YELLOW}  ⚠  Paso manual: modelo Qwen GGUF${NC}"
echo -e "${BOLD}${YELLOW}════════════════════════════════════════════════════${NC}"
echo ""
QWEN_DIR="$MODELS_DIR/qwen"
mkdir -p "$QWEN_DIR"

if ls "$QWEN_DIR"/*.gguf &>/dev/null 2>&1; then
    ok "Modelo GGUF ya presente en $QWEN_DIR"
else
    warn "No se encontró ningún modelo .gguf en $QWEN_DIR"
    echo ""
    echo "  Descárgalo de HuggingFace:"
    echo "  → https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF"
    echo "  Archivo recomendado: qwen2.5-0.5b-instruct-q4_k_m.gguf"
    echo "  Guárdalo en: $QWEN_DIR/"
    echo ""
    echo "  O con huggingface-cli (si lo tienes instalado):"
    echo "    pip install huggingface_hub"
    echo "    huggingface-cli download Qwen/Qwen2.5-0.5B-Instruct-GGUF \\"
    echo "      qwen2.5-0.5b-instruct-q4_k_m.gguf --local-dir $QWEN_DIR"
fi

# =============================================================================
# Keycode de la tecla Copilot
# =============================================================================
echo ""
echo -e "${BOLD}${YELLOW}════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${YELLOW}  ⚠  Paso manual: keycode de la tecla Copilot${NC}"
echo -e "${BOLD}${YELLOW}════════════════════════════════════════════════════${NC}"
echo ""
echo "  Ejecuta esto para encontrar el scancode de tu tecla:"
echo "    source .venv/bin/activate"
echo "    python tools/find_copilot_key.py"
echo ""
echo "  Luego edita jota/config.py:"
echo "    COPILOT_KEY_CODE = 0x???  ← tu scancode"

# =============================================================================
# Resumen final
# =============================================================================
echo ""
echo -e "${BOLD}${GREEN}════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}  ✅  Setup completado${NC}"
echo -e "${BOLD}${GREEN}════════════════════════════════════════════════════${NC}"
echo ""
echo "  Cuando tengas el modelo Qwen y el keycode configurado:"
echo ""
echo "    source .venv/bin/activate"
echo "    jota"
echo ""
if ! groups | grep -q '\binput\b'; then
    echo -e "  ${YELLOW}⚠  Recuerda re-loguearte para activar el grupo 'input'${NC}"
    echo ""
fi

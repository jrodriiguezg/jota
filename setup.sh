#!/usr/bin/env bash
# setup.sh — Guía de instalación de dependencias externas para Jota (Fase 1)
# Fedora Linux / Hyprland
# Ejecuta con: bash setup.sh

set -euo pipefail

MODELS_DIR="$HOME/.local/share/jota/models"
mkdir -p "$MODELS_DIR/whisper" "$MODELS_DIR/piper" "$MODELS_DIR/qwen"

echo "════════════════════════════════════════════════"
echo "  Jota — Setup de dependencias (Fase 1)"
echo "════════════════════════════════════════════════"

# ── 1. Grupo input para evdev ──────────────────────────────────────────────
echo ""
echo "► Añadiendo usuario al grupo 'input' (necesario para leer teclas sin sudo)..."
if ! groups | grep -q '\binput\b'; then
    sudo usermod -aG input "$USER"
    echo "  HECHO. Necesitas re-loguearte para que surta efecto."
else
    echo "  Ya estás en el grupo 'input'."
fi

# ── 2. Dependencias del sistema ────────────────────────────────────────────
echo ""
echo "► Instalando dependencias del sistema (Fedora)..."
sudo dnf install -y \
    portaudio-devel \
    libsndfile-devel \
    cmake \
    make \
    gcc-c++ \
    git

# ── 3. whisper.cpp ─────────────────────────────────────────────────────────
echo ""
echo "► Compilando whisper.cpp..."
WHISPER_DIR="/tmp/whisper.cpp-build"
if [ ! -d "$WHISPER_DIR" ]; then
    git clone --depth 1 https://github.com/ggerganov/whisper.cpp "$WHISPER_DIR"
fi
cmake -B "$WHISPER_DIR/build" -S "$WHISPER_DIR" -DCMAKE_BUILD_TYPE=Release
cmake --build "$WHISPER_DIR/build" --config Release -j"$(nproc)"
sudo install -m 755 "$WHISPER_DIR/build/bin/whisper-cpp" /usr/local/bin/whisper-cpp
echo "  whisper-cpp instalado en /usr/local/bin/whisper-cpp"

echo ""
echo "► Descargando modelo Whisper (small, ~244MB)..."
if [ ! -f "$MODELS_DIR/whisper/ggml-small.bin" ]; then
    curl -L "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin" \
         -o "$MODELS_DIR/whisper/ggml-small.bin" --progress-bar
    echo "  Modelo guardado en $MODELS_DIR/whisper/ggml-small.bin"
else
    echo "  Modelo ya existe, saltando."
fi

# ── 4. piper-tts ───────────────────────────────────────────────────────────
echo ""
echo "► Instalando piper-tts..."
PIPER_VERSION="2023.11.14-2"
PIPER_ARCH="amd64"
PIPER_TAR="piper_linux_${PIPER_ARCH}.tar.gz"
PIPER_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/${PIPER_TAR}"

if [ ! -f "/usr/bin/piper" ]; then
    curl -L "$PIPER_URL" -o "/tmp/$PIPER_TAR" --progress-bar
    tar -xzf "/tmp/$PIPER_TAR" -C /tmp/
    sudo install -m 755 /tmp/piper/piper /usr/bin/piper
    echo "  piper instalado en /usr/bin/piper"
else
    echo "  piper ya está instalado."
fi

echo ""
echo "► Descargando modelo de voz Piper (español)..."
PIPER_MODEL_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/sharvard/medium/es_ES-sharvard-medium.onnx"
PIPER_MODEL_JSON_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/sharvard/medium/es_ES-sharvard-medium.onnx.json"

if [ ! -f "$MODELS_DIR/piper/es_ES-sharvard-medium.onnx" ]; then
    curl -L "$PIPER_MODEL_URL" -o "$MODELS_DIR/piper/es_ES-sharvard-medium.onnx" --progress-bar
    curl -L "$PIPER_MODEL_JSON_URL" -o "$MODELS_DIR/piper/es_ES-sharvard-medium.onnx.json" --progress-bar
    echo "  Modelo piper guardado."
else
    echo "  Modelo piper ya existe."
fi

# ── 5. Modelo Qwen GGUF ────────────────────────────────────────────────────
echo ""
echo "► Para el modelo Qwen3.5:0.8b GGUF, descárgalo manualmente de HuggingFace:"
echo "  https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF"
echo "  O un modelo Q4_K_M que encaje en tu RAM."
echo "  Guárdalo en: $MODELS_DIR/qwen/"
echo "  Y actualiza LLM_MODEL en jota/config.py"

# ── 6. Entorno Python ──────────────────────────────────────────────────────
echo ""
echo "► Creando entorno virtual e instalando dependencias Python..."
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"

echo ""
echo "════════════════════════════════════════════════"
echo "  ✅  Setup completado."
echo ""
echo "  Próximos pasos:"
echo "  1. Re-loguéate si fue tu primera vez en el grupo 'input'."
echo "  2. Descarga el modelo Qwen GGUF y actualiza config.py."
echo "  3. Encuentra el keycode de tu tecla Copilot:"
echo "     source .venv/bin/activate"
echo "     python -m evdev.evtest"
echo "  4. Actualiza COPILOT_KEY_CODE en jota/config.py."
echo "  5. Ejecuta: jota"
echo "════════════════════════════════════════════════"

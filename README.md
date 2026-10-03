# Jota — Asistente de Voz Local

> Asistente de voz completamente **offline** para Fedora Linux / Hyprland.
> Activación por tecla Copilot → hablas → Jota responde.

---

## Stack técnico

| Componente | Tecnología |
|---|---|
| STT (voz → texto) | [`whisper.cpp`](https://github.com/ggerganov/whisper.cpp) (binario nativo) |
| LLM | [`llama-cpp-python`](https://github.com/abetlen/llama-cpp-python) + Qwen3.5:0.8b (GGUF) |
| TTS (texto → voz) | [`piper-tts`](https://github.com/rhasspy/piper) |
| Activación | Tecla **Copilot** via `evdev` (push-to-talk) |
| Lenguaje | Python 3.11+ |
| Target OS | Fedora Linux / Hyprland (Wayland) |

---

## Fases

| Fase | Estado | Descripción |
|---|---|---|
| **Fase 1** | En desarrollo | Oír y responder: Copilot → whisper → Qwen → piper |
| Fase 2 | Pendiente | Herramientas para el LLM (hora, clima, sistema…) |
| Fase 3 | Pendiente | Integración visual con Hyprland (overlay, notificaciones) |

---

## Requisitos previos

- Fedora Linux (o cualquier distro con `dnf` / `apt`)
- Python 3.11+
- Acceso de lectura a `/dev/input/*` (grupo `input`)
- ~2 GB de RAM libres para los modelos

---

## Instalación

### 1. Añadirte al grupo `input`

Necesario para leer la tecla Copilot sin `sudo`:

```bash
sudo usermod -aG input $USER
# Cierra sesión y vuelve a entrar para que surta efecto
```

Verifica que funciona:
```bash
groups | grep input
```

---

### 2. Dependencias del sistema (Fedora)

```bash
sudo dnf install -y \
    portaudio-devel \
    libsndfile-devel \
    cmake make gcc-c++ git curl
```

---

### 3. Compilar whisper.cpp

```bash
git clone --depth 1 https://github.com/ggerganov/whisper.cpp /tmp/whisper-build
cmake -B /tmp/whisper-build/build -S /tmp/whisper-build -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/whisper-build/build --config Release -j$(nproc)
sudo install -m 755 /tmp/whisper-build/build/bin/whisper-cpp /usr/local/bin/whisper-cpp
```

Verificar:
```bash
whisper-cpp --help
```

---

### 4. Descargar modelo de Whisper

```bash
mkdir -p ~/.local/share/jota/models/whisper
curl -L "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin" \
     -o ~/.local/share/jota/models/whisper/ggml-small.bin \
     --progress-bar
```

> **Nota:** El modelo `small` (~244 MB) es suficiente para comandos en español.
> Si tienes más RAM puedes usar `ggml-medium.bin` para mejor precisión.

Modelos disponibles: https://huggingface.co/ggerganov/whisper.cpp

---

### 5. Instalar piper-tts

```bash
# Descarga el binario precompilado para Linux x86_64
PIPER_VER="2023.11.14-2"
curl -L "https://github.com/rhasspy/piper/releases/download/${PIPER_VER}/piper_linux_amd64.tar.gz" \
     -o /tmp/piper.tar.gz --progress-bar
tar -xzf /tmp/piper.tar.gz -C /tmp/
sudo install -m 755 /tmp/piper/piper /usr/bin/piper
```

Verificar:
```bash
piper --help
```

---

### 6. Descargar modelo de voz Piper (español)

```bash
mkdir -p ~/.local/share/jota/models/piper

# Voz: es_ES-sharvard-medium (español neutro, buena calidad)
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/sharvard/medium"
curl -L "${BASE}/es_ES-sharvard-medium.onnx" \
     -o ~/.local/share/jota/models/piper/es_ES-sharvard-medium.onnx --progress-bar
curl -L "${BASE}/es_ES-sharvard-medium.onnx.json" \
     -o ~/.local/share/jota/models/piper/es_ES-sharvard-medium.onnx.json --progress-bar
```

Probar que funciona:
```bash
echo "Hola, soy Jota, tu asistente de voz." | piper \
    --model ~/.local/share/jota/models/piper/es_ES-sharvard-medium.onnx \
    --output_file /tmp/test.wav && aplay /tmp/test.wav
```

Otros modelos de voz en español: https://huggingface.co/rhasspy/piper-voices/tree/main/es

---

### 7. Descargar modelo Qwen GGUF

El modelo LLM hay que descargarlo manualmente de HuggingFace:

```bash
mkdir -p ~/.local/share/jota/models/qwen
```

Ve a: https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF

Descarga el archivo `qwen2.5-0.5b-instruct-q4_k_m.gguf` y ponlo en:
```
~/.local/share/jota/models/qwen/
```

> **¿Por qué Qwen2.5-0.5B y no 3.5-0.8B?**
> Qwen3.5:0.8b aún no tiene GGUF oficial en HuggingFace al momento de escribir esto.
> El 2.5-0.5B es el más cercano en tamaño y también usa formato ChatML.
> Actualiza `LLM_MODEL` en `jota/config.py` con el nombre exacto del archivo que descargues.

---

### 8. Entorno Python

```bash
# Clona el repo si aún no lo tienes
git clone https://git.jrodriiguezg.link/jrodriiguezg/jota.git
cd jota

# Crea el entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instala el proyecto y sus dependencias
pip install --upgrade pip
pip install -e ".[dev]"
```

---

### 9. Encontrar el keycode de tu tecla Copilot

La tecla Copilot tiene distintos keycodes según el teclado/kernel.
Usa la herramienta incluida para encontrar el tuyo:

```bash
source .venv/bin/activate
python tools/find_copilot_key.py
```

Selecciona tu teclado, pulsa la tecla Copilot y anota el `scancode` (en hex).
Luego edita `jota/config.py`:

```python
COPILOT_KEY_CODE = 0x1D8  # ← reemplaza con tu valor
```

> **Tip:** Si no ves nada al pulsar Copilot, prueba con `sudo python tools/find_copilot_key.py`
> para descartar problemas de permisos antes de re-loguear.

---

### 10. Verificar la configuración

Abre [`jota/config.py`](jota/config.py) y revisa:

```python
WHISPER_BIN   = Path("/usr/local/bin/whisper-cpp")   # ¿existe?
WHISPER_MODEL = MODELS_DIR / "whisper" / "ggml-small.bin"  # ¿descargado?
LLM_MODEL     = MODELS_DIR / "qwen" / "qwen2.5-0.5b-instruct-q4_k_m.gguf"  # nombre exacto
PIPER_BIN     = Path("/usr/bin/piper")                # ¿existe?
PIPER_MODEL   = MODELS_DIR / "piper" / "es_ES-sharvard-medium.onnx"  # ¿descargado?
COPILOT_KEY_CODE = 0x1D8  # ¿tu scancode?
```

---

## Ejecutar

```bash
source .venv/bin/activate
jota
```

Verás algo así:
```
12:34:56 [INFO] jota: ══════════════════════════════════════════════════
12:34:56 [INFO] jota:   Jota — Asistente de voz local  (Fase 1)
12:34:56 [INFO] jota: ══════════════════════════════════════════════════
12:34:56 [INFO] jota: Cargando modelo LLM, espera un momento...
12:35:02 [INFO] jota: Modelo listo.
12:35:02 [INFO] jota: Listo. Mantén pulsada la tecla Copilot y habla.
```

**Uso:**
1. Mantén **pulsada** la tecla Copilot
2. Di algo como: *"Jota, ¿cómo estás?"*
3. Suelta la tecla
4. Jota transcribe, procesa y responde en voz alta

> La palabra "Jota" (o "Hota") al inicio se elimina automáticamente antes de pasar la frase al LLM.

---

## Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

---

## Estructura del proyecto

```
jota/
├── jota/
│   ├── config.py      # Rutas de modelos y configuración
│   ├── main.py        # Punto de entrada y orquestación
│   ├── audio.py       # Grabación desde micrófono (sounddevice)
│   ├── stt.py         # STT: whisper.cpp + limpieza de wake word
│   ├── llm.py         # LLM: llama-cpp-python + Qwen
│   └── tts.py         # TTS: piper-tts + reproducción de audio
├── tests/
│   └── test_stt.py    # Tests de detección del wake word
├── tools/
│   └── find_copilot_key.py  # Diagnóstico del keycode Copilot
├── setup.sh           # Script de instalación automática
└── pyproject.toml     # Dependencias Python
```

---

## Solución de problemas

### "Permission denied" al leer /dev/input/*
```bash
sudo usermod -aG input $USER
# Re-loguéate y prueba de nuevo
```

### whisper.cpp no transcribe bien en español
Asegúrate de tener `WHISPER_LANG = "es"` en `config.py`.

### El audio no se graba / reproduce
```bash
# Verifica que sounddevice detecta tu micrófono y altavoces
python -c "import sounddevice; print(sounddevice.query_devices())"
```

### llama-cpp-python tarda mucho compilando
```bash
# Instala las wheels precompiladas (CPU only)
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

---

## Contribuir / Roadmap

Próximas fases planeadas:
- **Fase 2:** Sistema de herramientas (tools) para el LLM — hora, clima, búsquedas, control del sistema
- **Fase 3:** Overlay visual en Hyprland con estado del asistente

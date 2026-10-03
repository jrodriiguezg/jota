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

### Método Automático (Recomendado)

Ejecuta el script incluido. Se encarga de todo:
- Verifica e instala paquetes de sistema necesarios
- Compila `whisper-cli`
- Descarga el modelo Whisper `ggml-small.bin`
- Instala `piper-tts` en espacio de usuario (`~/.local/share/jota/piper`)
- Descarga el modelo de voz en español (`es_ES-sharvard-medium.onnx`)
- Descarga el modelo LLM `qwen2.5-0.5b-instruct-q4_k_m.gguf`
- Crea el entorno virtual e instala dependencias Python
- Ejecuta pruebas automáticas de síntesis y respuesta del LLM

```bash
git clone git@github.com:jrodriiguezg/jota.git
cd jota
bash setup.sh
```

---

### Configuración de la Tecla Copilot (Push-to-Talk)

Para encontrar el scancode de tu teclado:

```bash
source .venv/bin/activate
python tools/find_copilot_key.py
```

Pulsa la tecla Copilot y anota el código (ejemplo: `0x1d8` o el que aparezca en pantalla). Luego verifica en `jota/config.py`:

```python
COPILOT_KEY_CODE = 0x1D8  # actualiza si tu teclado usa otro valor
```

> **Permisos de teclado**: Si no estás en el grupo `input`, ejecuta una vez `sudo usermod -aG input $USER` y cierra sesión para activar el permiso de lectura de eventos de teclado.

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

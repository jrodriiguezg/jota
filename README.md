# Jota — Asistente de Voz Local

> Asistente de voz completamente **offline** para Fedora Linux / Hyprland.
> Activacion por tecla Copilot -> hablas -> Jota responde.

---

## Stack tecnico

| Componente | Tecnologia |
|---|---|
| STT (voz -> texto) | [`whisper.cpp`](https://github.com/ggerganov/whisper.cpp) (binario nativo `whisper-cli`) |
| LLM | [`llama-cpp-python`](https://github.com/abetlen/llama-cpp-python) + [`Qwen3-0.6B-GGUF`](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF) (`Qwen3-0.6B-Q8_0.gguf`) |
| TTS (texto -> voz) | [`piper-tts`](https://github.com/rhasspy/piper) (`es_ES-sharvard-medium.onnx`) |
| Activacion | Tecla **Copilot** via `evdev` (push-to-talk) |
| Lenguaje | Python 3.11+ |
| Target OS | Fedora Linux / Hyprland (Wayland) |

---

## Fases

| Fase | Estado | Descripcion |
|---|---|---|
| **Fase 1** | En desarrollo | Oir y responder: Copilot -> whisper -> Qwen3 -> piper |
| Fase 2 | Pendiente | Herramientas para el LLM (hora, clima, sistema...) |
| Fase 3 | Pendiente | Integracion visual con Hyprland (overlay, notificaciones) |

---

## Requisitos previos

- Fedora Linux (o cualquier distro con `dnf` / `apt`)
- Python 3.11+
- Acceso de lectura a `/dev/input/*` (grupo `input`)
- ~2 GB de RAM libres para los modelos

---

## Instalacion

### Metodo Automatico (Recomendado)

Ejecuta el script incluido. Se encarga de todo:
- Verifica e instala paquetes de sistema necesarios
- Compila `whisper-cli`
- Descarga el modelo Whisper `ggml-small.bin`
- Instala `piper-tts` en espacio de usuario (`~/.local/bin/piper`)
- Descarga el modelo de voz en espanol (`es_ES-sharvard-medium.onnx`)
- Descarga el modelo LLM `Qwen3-0.6B-Q8_0.gguf`
- Crea el entorno virtual e instala dependencias Python
- Ejecuta pruebas automaticas de sintesis y respuesta del LLM

```bash
git clone git@github.com:jrodriiguezg/jota.git
cd jota
bash setup.sh
```

---

## Modelo LLM: Qwen3-0.6B

Jota utiliza el modelo **Qwen3-0.6B** en formato GGUF (`Qwen3-0.6B-Q8_0.gguf`).

### Modo Non-Thinking (Por defecto) vs Thinking

Qwen3 incluye capacidades nativas de razonamiento interno mediante bloques `<think>...</think>`. Para un asistente de voz interactivo y ejecucion de herramientas, la latencia es critica:

- **Modo Non-Thinking (`/no_think`) — Activo por defecto:**
  Configurado con `LLM_ENABLE_THINKING = False` en `jota/config.py`. Se anexa la directiva `/no_think` al prompt del sistema. El modelo omite la generacion de tokens de pensamiento interno y responde directamente, reduciendo el tiempo de respuesta en CPU de ~45 segundos a ~1.4 segundos.
- **Modo Thinking (`/think`):**
  Puedes activar el razonamiento estableciendo `LLM_ENABLE_THINKING = True` en `jota/config.py` o anadiendo `/think` en cualquier peticion puntual. Jota filtra automaticamente las etiquetas `<think>` para que el motor de voz TTS solo lea la respuesta final.

### Parametros de Muestreo Oficiales

Siguiendo las recomendaciones oficiales de Alibaba Cloud para Qwen3 en modo no-pensamiento y modelos cuantizados, Jota implementa:

| Parametro | Valor | Proposito |
|---|---|---|
| `temperature` | `0.7` | Equilibrio optimo entre creatividad y precision |
| `top_p` | `0.8` | Nucleus sampling recomendado para respuestas coherentes |
| `top_k` | `20` | Acota la seleccion a los tokens mas probables |
| `presence_penalty` | `1.5` | Evita problemas de repeticion en modelos cuantizados |

---

## Configuracion de la Tecla Copilot (Push-to-Talk)

Para identificar el scancode emitido por la tecla Copilot en tu teclado:

```bash
source .venv/bin/activate
python tools/find_copilot_key.py
```

Selecciona tu teclado, pulsa la tecla Copilot y anota el codigo detectado (por ejemplo `0x00c1` / `193` para `KEY_F23` o `0x1d8`). Luego verifica en `jota/config.py`:

```python
COPILOT_KEY_CODE = 0x00C1  # scancode asignado en tu teclado
```

> **Permisos de teclado**: Si no estas en el grupo `input`, ejecuta una vez `sudo usermod -aG input $USER` y reinicia sesion para activar los permisos de lectura de eventos de teclado sin requerir privilegios de superusuario.

---

## Verificar la configuracion

Abre [`jota/config.py`](jota/config.py) y revisa las variables principales:

```python
WHISPER_BIN   = Path("/usr/local/bin/whisper-cli")
WHISPER_MODEL = MODELS_DIR / "whisper" / "ggml-small.bin"
LLM_MODEL     = MODELS_DIR / "qwen" / "Qwen3-0.6B-Q8_0.gguf"
PIPER_BIN     = Path.home() / ".local" / "bin" / "piper"
PIPER_MODEL   = MODELS_DIR / "piper" / "es_ES-sharvard-medium.onnx"
COPILOT_KEY_CODE = 0x00C1
```

---

## Ejecutar

```bash
source .venv/bin/activate
jota
```

Salida esperada:
```
12:34:56 [INFO] jota: ==================================================
12:34:56 [INFO] jota:   Jota — Asistente de voz local  (Fase 1)
12:34:56 [INFO] jota: ==================================================
12:34:56 [INFO] jota: Cargando modelo LLM, espera un momento...
12:35:00 [INFO] jota: Modelo listo.
12:35:00 [INFO] jota: Listo. Manten pulsada la tecla Copilot y habla.
```

**Uso:**
1. Manten **pulsada** la tecla Copilot.
2. Di algo como: *"Jota, ¿como estas?"* (o *"J, ¿como estas?"*).
3. Suelta la tecla.
4. Jota transcribe, procesa y responde en voz alta.

> Las palabras de activacion como *"Jota"*, *"Hota"* o *"J"* al inicio se limpian automaticamente antes de enviar la frase al LLM.

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
│   ├── config.py      # Rutas de modelos, parametros LLM y configuracion
│   ├── main.py        # Punto de entrada y orquestacion push-to-talk
│   ├── audio.py       # Grabacion desde microfono (sounddevice)
│   ├── stt.py         # STT: whisper.cpp + limpieza de wake word
│   ├── llm.py         # LLM: llama-cpp-python + Qwen3 (/no_think por defecto)
│   └── tts.py         # TTS: piper-tts + reproduccion de audio
├── tests/
│   ├── test_llm.py    # Tests de limpieza de texto y modos de prompt LLM
│   └── test_stt.py    # Tests de deteccion y extraccion del wake word
├── tools/
│   └── find_copilot_key.py  # Diagnostico y deteccion del keycode Copilot
├── setup.sh           # Script de instalacion y setup automatico
└── pyproject.toml     # Configuracion de paquete y dependencias Python
```

---

## Solucion de problemas

### "Permission denied" al leer /dev/input/*
```bash
sudo usermod -aG input $USER
# Cierra sesion y vuelve a iniciar sesion
```

### whisper.cpp no transcribe bien en espanol
Asegurate de tener `WHISPER_LANG = "es"` en `config.py`.

### El audio no se graba o reproduce
```bash
# Verifica que sounddevice detecta tu microfono y altavoces
python -c "import sounddevice; print(sounddevice.query_devices())"
```

### llama-cpp-python tarda mucho compilando
```bash
# Instala las wheels precompiladas (CPU only)
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

---

## Contribuir / Roadmap

Proximas fases planeadas:
- **Fase 2:** Sistema de herramientas (tools) para el LLM — hora, clima, busquedas, control del sistema
- **Fase 3:** Overlay visual en Hyprland con estado del asistente

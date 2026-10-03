# Jota — Asistente de Voz Local (v0.2.0)

> Asistente de voz completamente **offline** para Fedora Linux / Hyprland.
> Activacion por tecla Copilot -> hablas -> Jota responde o ejecuta herramientas del sistema.

---

## Stack tecnico

| Componente | Tecnologia |
|---|---|
| STT (voz -> texto) | [`whisper.cpp`](https://github.com/ggerganov/whisper.cpp) (binario nativo `whisper-cli`) |
| LLM | [`llama-cpp-python`](https://github.com/abetlen/llama-cpp-python) + [`Qwen3-0.6B-GGUF`](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF) (`Qwen3-0.6B-Q8_0.gguf`) |
| TTS (texto -> voz) | [`piper-tts`](https://github.com/rhasspy/piper) (`es_ES-sharvard-medium.onnx`) |
| Herramientas | `wpctl` (PipeWire), `playerctl`, `grim`, `wl-copy`, `gtk-launch`, `xdg-mime`, `firefox` |
| Activacion | Tecla **Copilot** via `evdev` (push-to-talk) |
| Lenguaje | Python 3.11+ |
| Target OS | Fedora Linux / Hyprland (Wayland) |

---

## Fases del proyecto

| Fase | Estado | Descripcion |
|---|---|---|
| **Fase 1** | Completada | Oir y responder: Copilot -> whisper -> Qwen3 -> piper |
| **Fase 2** | Implementada (v0.2) | Herramientas locales: multimedia, volumen, capturas, apertura de apps, busqueda web |
| Fase 3 | Pendiente | Integracion visual con Hyprland (overlay, notificaciones) |

---

## Herramientas del Sistema (Fase 2)

Jota implementa una arquitectura en dos niveles para una ejecucion ultra-rapida:
1. **Nivel 1 — Enrutador Rapido de Intenciones (<10 ms):** Reconoce patrones y comandos comunes al instante sin esperar la inferencia del LLM.
2. **Nivel 2 — LLM Tool Calling:** Si la peticion es formulada de forma compleja o conversacional, el LLM emite directivas `TOOL: nombre(argumentos)` que son parseadas y ejecutadas.

### 1. Control Multimedia y Volumen
- **Volumen:** "sube el volumen", "baja el volumen", "aumenta el sonido", "menos volumen".
  - Controla el sink predeterminado mediante PipeWire/WirePlumber (`wpctl set-volume`) con fallback a PulseAudio (`pactl`).
  - Paso configurable en `config.py` (`VOLUME_STEP_PERCENT = 5`).
- **Silencio:** "silencia el audio", "mute", "quitar silencio".
- **Reproduccion MPRIS:** "pausa la musica", "reproduce", "siguiente cancion", "cambia de cancion", "cancion anterior", "para la musica".
  - Controla reproductores activos (Feishin, Chromium, Spotify, etc.) via `playerctl`.

### 2. Captura de Pantalla en el Portapapeles
- **Comandos:** "captura pantalla", "haz una captura de pantalla", "copia la pantalla en el portapapeles", "screenshot".
- **Comportamiento:** Utiliza `grim` para capturar la composicion Wayland y la pasa directamente al portapapeles con `wl-copy --type image/png`. Responde por voz: *"Captura de pantalla copiada al portapapeles."*

### 3. Apertura de Aplicaciones y Resolucion MIME
- **Por nombre o comando:** "abre dolphin", "abre firefox", "abre terminal", "abre kitty".
- **Por tipo MIME estandar:** "abre el explorador de archivos" o "abre el gestor de archivos" consulta `xdg-mime query default inode/directory` (en tu sistema abre Dolphin).
- **Mapeos y alias personalizados:**
  - "abre el reproductor de musica", "abre feishin", "abre feisfin", "abre la musica" -> resuelve y lanza el reproductor configurado (`org.jeffvli.feishin`).
  - Configurable directamente en `jota/config.py` (`CUSTOM_APP_MAPPINGS` y `APP_ALIASES`).

### 4. Busqueda Web
- **Comandos:** "buscame en la web que es una vaca", "busca en google recetas faciles", "busca en internet historia de linux".
- **Comportamiento:** Abre Firefox (`BROWSER_BIN = "firefox"`) con la consulta codificada en Google (`https://www.google.com/search?q=...`) en segundo plano sin bloquear el asistente y confirma por voz: *"Buscando en la web: que es una vaca."*

---

## Modelo LLM: Qwen3-0.6B

Jota utiliza el modelo **Qwen3-0.6B** en formato GGUF (`Qwen3-0.6B-Q8_0.gguf`).

### Modo Non-Thinking (Por defecto) vs Thinking

- **Modo Non-Thinking (`/no_think`) — Activo por defecto:**
  Configurado con `LLM_ENABLE_THINKING = False` en `jota/config.py`. Se anexa la directiva `/no_think` al prompt del sistema. El modelo omite la generacion de razonamiento interno `<think>...</think>`, respondiendo en CPU en ~1.4 segundos en vez de ~45 segundos.
- **Modo Thinking (`/think`):**
  Se puede activar globalmente con `LLM_ENABLE_THINKING = True` o solicitando `/think` en un turno puntual. Jota filtra los bloques `<think>` para que el motor de voz TTS solo lea la respuesta final.

### Parametros de Muestreo Oficiales

| Parametro | Valor | Proposito |
|---|---|---|
| `temperature` | `0.7` | Equilibrio optimo entre creatividad y precision |
| `top_p` | `0.8` | Nucleus sampling recomendado para respuestas coherentes |
| `top_k` | `20` | Acota la seleccion a los tokens mas probables |
| `presence_penalty` | `1.5` | Evita problemas de repeticion en modelos cuantizados |

---

## Requisitos previos

- Fedora Linux (o cualquier distro con `dnf` / `apt`)
- Python 3.11+
- Paquetes multimedia y Wayland: `grim`, `wl-clipboard`, `playerctl`, `wireplumber` / `pipewire-utils`
- Acceso de lectura a `/dev/input/*` (grupo `input`)
- ~2 GB de RAM libres para los modelos

---

## Instalacion

### Metodo Automatico (Recomendado)

Ejecuta el script incluido:

```bash
git clone git@github.com:jrodriiguezg/jota.git
cd jota
bash setup.sh
```

El script instala dependencias del sistema, compila `whisper-cli`, descarga los modelos (Whisper, Piper y Qwen3-0.6B) y prepara el entorno virtual.

---

## Configuracion de la Tecla Copilot (Push-to-Talk)

Para identificar el scancode emitido por la tecla Copilot en tu teclado:

```bash
source .venv/bin/activate
python tools/find_copilot_key.py
```

Selecciona tu teclado, pulsa la tecla Copilot y anota el codigo detectado (por ejemplo `0x00c1` / `193` para `KEY_F23`). Luego verifica en `jota/config.py`:

```python
COPILOT_KEY_CODE = 0x00C1  # scancode asignado en tu teclado
```

> **Permisos de teclado**: Si no estas en el grupo `input`, ejecuta una vez `sudo usermod -aG input $USER` y reinicia sesion para activar los permisos de lectura de eventos de teclado sin requerir privilegios de superusuario.

---

## Ejecutar

```bash
source .venv/bin/activate
jota
```

Salida esperada:
```
12:34:56 [INFO] jota: ==================================================
12:34:56 [INFO] jota:   Jota — Asistente de voz local  (Fase 2)
12:34:56 [INFO] jota: ==================================================
12:34:56 [INFO] jota: Cargando modelo LLM, espera un momento...
12:35:00 [INFO] jota: Modelo listo.
12:35:00 [INFO] jota: Listo. Manten pulsada la tecla Copilot y habla.
```

**Ejemplos de uso por voz:**
1. *"Jota, sube el volumen"* -> Sube volumen de PipeWire y responde "Volumen subido al 85%."
2. *"Jota, pausa la musica"* -> Pausa la reproduccion actual via playerctl.
3. *"Jota, captura pantalla"* -> Toma captura completa y la copia al portapapeles.
4. *"Jota, abre el explorador de archivos"* -> Abre Dolphin mediante resolucion MIME.
5. *"Jota, abre el reproductor de musica"* -> Abre Feishin.
6. *"Jota, buscame en la web que es una vaca"* -> Abre Firefox con la busqueda en Google.
7. *"Jota, ¿por que el cielo es azul?"* -> Responde mediante el LLM en modo conciso.

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
│   ├── config.py         # Rutas, parametros LLM, alias y configuracion de herramientas
│   ├── main.py           # Orquestacion del bucle push-to-talk y despacho
│   ├── audio.py          # Grabacion desde microfono (sounddevice)
│   ├── stt.py            # STT: whisper.cpp + limpieza de wake word
│   ├── llm.py            # LLM: llama-cpp-python + Qwen3 (/no_think)
│   ├── tts.py            # TTS: piper-tts + reproduccion de audio
│   └── tools/            # Herramientas del sistema (Fase 2)
│       ├── __init__.py   # Punto de entrada de despacho de herramientas
│       ├── router.py     # Enrutador rapido de intenciones y parser LLM
│       ├── media.py      # Control de volumen (wpctl) y reproduccion (playerctl)
│       ├── screenshot.py # Capturas Wayland (grim + wl-copy)
│       ├── apps.py       # Resolucion de aplicaciones, MIME types y Flatpak
│       └── search.py     # Busqueda web con Firefox y Google
├── tests/
│   ├── test_llm.py       # Tests de limpieza de texto y modos de prompt LLM
│   ├── test_stt.py       # Tests de deteccion y extraccion del wake word
│   └── test_tools.py     # Tests de enrutador, parser y ejecucion de herramientas
├── tools/
│   └── find_copilot_key.py  # Diagnostico y deteccion del keycode Copilot
├── setup.sh              # Script de instalacion y setup automatico
└── pyproject.toml        # Configuracion de paquete y dependencias Python
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
python -c "import sounddevice; print(sounddevice.query_devices())"
```

### grim o wl-copy no encuentran la pantalla
Asegurate de que las variables de entorno `WAYLAND_DISPLAY` y `XDG_CURRENT_DESKTOP` esten definidas en tu sesion de Hyprland.

"""
Configuración central de Jota.
Edita aquí las rutas a los modelos y preferencias.
"""

import os
import shutil
from pathlib import Path

# ── Rutas de modelos ─────────────────────────────────────────────────────────

# Directorio raíz donde están los modelos
MODELS_DIR = Path.home() / ".local" / "share" / "jota" / "models"

# Whisper: ruta al binario de whisper.cpp
# Nota: en versiones recientes el binario se llama whisper-cli (antes whisper-cpp)
_local_whisper = Path.home() / ".local" / "bin" / "whisper-cli"
WHISPER_BIN = (
    _local_whisper
    if _local_whisper.is_file() and os.access(_local_whisper, os.X_OK)
    else Path(shutil.which("whisper-cli") or "/usr/local/bin/whisper-cli")
)
# Modelo de whisper a usar (small es suficiente para comandos en español)
WHISPER_MODEL = MODELS_DIR / "whisper" / "ggml-small.bin"
# Idioma de reconocimiento
WHISPER_LANG = "es"

# LLM: modelo GGUF de Qwen (por defecto Qwen3-0.6B)
_default_qwen = MODELS_DIR / "qwen" / "Qwen3-0.6B-Q8_0.gguf"
_found_ggufs = sorted(
    (MODELS_DIR / "qwen").glob("*.gguf"),
    key=lambda p: (not p.name.startswith("Qwen3"), p.name),
) if (MODELS_DIR / "qwen").exists() else []
LLM_MODEL = _found_ggufs[0] if _found_ggufs else _default_qwen
LLM_N_CTX = 2048          # contexto de tokens
LLM_N_GPU_LAYERS = 0       # 0 = sólo CPU; -1 = todo en GPU si tienes CUDA/Vulkan

# Parametros de muestreo para ejecucion precisa de herramientas:
LLM_TEMPERATURE = 0.1
LLM_TOP_P = 0.8
LLM_TOP_K = 20
LLM_PRESENCE_PENALTY = 0.0

# Modo de razonamiento (pensamiento):
# False = /no_think por defecto (recomendado para asistente de voz, respuesta instantanea)
# True  = /think (permite cadena de pensamiento interna <think>...</think>)
LLM_ENABLE_THINKING = False

# TTS: piper-tts
PIPER_BIN = Path(shutil.which("piper") or (Path.home() / ".local" / "bin" / "piper"))
PIPER_MODEL = MODELS_DIR / "piper" / "es_ES-sharvard-medium.onnx"

# ── Wake word ────────────────────────────────────────────────────────────────

# Palabras que activan el asistente (en minúsculas).
# Se eliminan del inicio de la frase antes de pasar al LLM.
WAKE_WORDS = ["jota", "hota", "j"]  # Whisper transcribe frecuentemente 'J' a secas

# En modo push-to-talk (tecla Copilot), no es necesario decir la wake word.
# La wake word se reserva para activacion manos libres (sin teclas).
REQUIRE_WAKE_WORD = False

# ── Audio ────────────────────────────────────────────────────────────────────

AUDIO_SAMPLE_RATE = 16000   # Hz (whisper.cpp espera 16kHz)
AUDIO_CHANNELS = 1
AUDIO_DTYPE = "int16"
# Duración máxima de grabación en segundos (por si no suelta la tecla)
AUDIO_MAX_DURATION = 30

# Directorio y archivo temporal seguro para el audio grabado
AUDIO_TMP_DIR = Path.home() / ".local" / "share" / "jota" / "tmp"
AUDIO_TMP_FILE = AUDIO_TMP_DIR / "input.wav"

# ── Hotkey ───────────────────────────────────────────────────────────────────

# Codigo de la tecla Copilot detectado en tu hardware:
# Al pulsar la tecla Copilot, el teclado emite KEY_F23 (scancode 0x00c1 = 193)
COPILOT_KEY_CODE = 0x00C1
COPILOT_KEY_CODES = {0x00C1, 0x1D8, 193, 472}

# ── Herramientas (Fase 2) ────────────────────────────────────────────────────

VOLUME_STEP_PERCENT = 5
BROWSER_BIN = "firefox"
WEB_SEARCH_URL = "https://www.google.com/search?q="

# Tipos de aplicaciones estandar asignados a MIME types o comandos
DEFAULT_MIME_TYPES = {
    "explorador_archivos": "inode/directory",
    "navegador": "x-scheme-handler/https",
    "editor_texto": "text/plain",
}

# Aplicaciones preferidas personalizadas por el usuario
CUSTOM_APP_MAPPINGS = {
    "musica": "org.jeffvli.feishin",
    "reproductor_musica": "org.jeffvli.feishin",
    "reproductor_multimedia": "org.jeffvli.feishin",
}

# Variantes y alias comunes en lenguaje natural mapeados a nombres de app o mimes
APP_ALIASES = {
    # Explorador de archivos
    "explorador de archivos": "inode/directory",
    "explorador": "inode/directory",
    "gestor de archivos": "inode/directory",
    "archivos": "inode/directory",
    "carpetas": "inode/directory",
    "dolphin": "org.kde.dolphin",
    "explorer": "inode/directory",
    # Musica y multimedia
    "reproductor de musica": "org.jeffvli.feishin",
    "reproductor multimedia": "org.jeffvli.feishin",
    "reproductor de audio": "org.jeffvli.feishin",
    "reproductor": "org.jeffvli.feishin",
    "musica": "org.jeffvli.feishin",
    "feishin": "org.jeffvli.feishin",
    "feisfin": "org.jeffvli.feishin",
    # Navegadores
    "navegador": "firefox",
    "navegador web": "firefox",
    "firefox": "firefox",
    "google chrome": "google-chrome",
    "chromium": "chromium",
    # Terminal
    "terminal": "kitty",
    "consola": "kitty",
    "kitty": "kitty",
    "konsole": "konsole",
}

# ── Sistema prompt del LLM ───────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres Jota, un asistente de voz local para Linux.
Deduce la intencion del usuario incluso si la transcripcion de voz tiene errores foneticos.
Responde siempre de forma breve, concisa y sin emojis.

Si el usuario quiere ejecutar una accion, responde EXACTAMENTE en este formato:
TOOL: <nombre>(<parametros>)
<mensaje breve para decir en voz alta>

Ejemplos:
Usuario: habla terminal
TOOL: open_app(name='terminal')
Abriendo la terminal.

Usuario: a ver a terminar
TOOL: open_app(name='terminal')
Abriendo la terminal.

Usuario: habla la terminal
TOOL: open_app(name='terminal')
Abriendo la terminal.

Usuario: abre una terminal
TOOL: open_app(name='terminal')
Abriendo la terminal.

Usuario: abre feisfin
TOOL: open_app(name='feishin')
Abriendo Feishin.

Usuario: abre el reproductor de musica
TOOL: open_app(name='feishin')
Abriendo Feishin.

Usuario: abre el explorador de archivos
TOOL: open_app(name='dolphin')
Abriendo el explorador de archivos.

Usuario: sube el volumen
TOOL: volume_control(action='up')
Subiendo el volumen.

Usuario: baja el volumen
TOOL: volume_control(action='down')
Bajando el volumen.

Usuario: silencia el audio
TOOL: volume_control(action='mute')
Silenciando el audio.

Usuario: pausa la musica
TOOL: media_control(action='pause')
Pausando la musica.

Usuario: siguiente cancion
TOOL: media_control(action='next')
Siguiente cancion.

Usuario: cancion anterior
TOOL: media_control(action='previous')
Cancion anterior.

Usuario: captura de pantalla
TOOL: screenshot()
Haciendo captura de pantalla.

Usuario: buscame en la web que es una vaca
TOOL: web_search(query='que es una vaca')
Buscando en la web que es una vaca.

Usuario: encuentra mi movil
TOOL: phone_control(action='ring')
Haciendo sonar tu telefono.

Usuario: haz sonar mi telefono
TOOL: phone_control(action='ring')
Haciendo sonar tu telefono.

Usuario: cuanta bateria le queda al movil
TOOL: phone_control(action='status')
Consultando el estado de tu telefono.

Usuario: envia al movil este enlace https://google.com
TOOL: phone_control(action='open_url', value='https://google.com')
Enviando el enlace a tu telefono.

Usuario: bloquea el pc
TOOL: lock_pc()
Bloqueando el PC.

Usuario: suspende el equipo
TOOL: system_power(action='suspend')
Suspendiendo el equipo.

Usuario: cierra la ventana
TOOL: close_active_window()
Cerrando ventana.

Usuario: como esta el pc
TOOL: pc_summary()
Consultando el estado del equipo.

Usuario: manda una notificacion con el texto hola mundo
TOOL: send_notification(title='Jota', message='hola mundo')
Enviando notificacion al escritorio.

Usuario: enciende la linterna del movil
TOOL: phone_control(action='torch', value='on')
Encendiendo linterna del movil.

Usuario: apaga la linterna del movil
TOOL: phone_control(action='torch', value='off')
Apagando linterna del movil.

Usuario: pon el movil en silencio
TOOL: phone_control(action='silent', value='on')
Poniendo el movil en silencio.

Usuario: manda al movil la ultima captura
TOOL: phone_control(action='send_file', value='captura')
Enviando la ultima captura a tu telefono.

Usuario: pasa al escritorio 2
TOOL: switch_workspace(target=2)
Cambiando al escritorio 2.

Usuario: mueve la ventana al escritorio 3
TOOL: move_to_workspace(target=3)
Moviendo ventana al escritorio 3.

Usuario: que tiempo hace en Madrid
TOOL: get_weather(city='Madrid')
Consultando el tiempo en Madrid.

Usuario: va a llover hoy
TOOL: get_weather(city='Madrid')
Consultando si va a llover.

Usuario: anota comprar cafe
TOOL: manage_notes(action='add', text='comprar cafe')
Guardando nota.

Usuario: que notas tengo pendientes
TOOL: manage_notes(action='list')
Consultando tus notas.

Usuario: avisame en 10 minutos para la pizza
TOOL: set_timer(seconds=600, label='la pizza')
Iniciando temporizador de 10 minutos para la pizza.

Usuario: hola como estas
Hola, estoy listo para ayudarte.

Usuario: por que el cielo es azul
El cielo es azul por la dispersion de la luz solar en la atmosfera."""

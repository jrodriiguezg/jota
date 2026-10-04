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

# LLM: seleccion dinamica del modelo GGUF mas capaz disponible
def _resolve_llm_model() -> Path:
    env_model = os.getenv("JOTA_LLM_MODEL")
    if env_model and Path(env_model).is_file():
        return Path(env_model)

    qwen_dir = MODELS_DIR / "qwen"
    if qwen_dir.exists():
        ggufs = list(qwen_dir.glob("*.gguf"))
        if ggufs:
            # Ordenar por tamano de archivo descendente para elegir el modelo de mayor capacidad
            ggufs.sort(key=lambda p: p.stat().st_size, reverse=True)
            return ggufs[0]
    return MODELS_DIR / "qwen" / "Qwen3-0.6B-Q8_0.gguf"


LLM_MODEL = _resolve_llm_model()
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

# ── Indicador Visual de Pantalla (Orbe Flotante Wayland) ─────────────────────

ORB_ENABLED = True
ORB_SIZE = 140
ORB_CORNER = "bottom_right"  # "bottom_right", "bottom_left", "top_right", "top_left"
ORB_MARGIN_X = 28
ORB_MARGIN_Y = 28
ORB_FPS = 60
ORB_SOCKET_PATH = Path("/tmp/jota_orb.sock")

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
    "fire fox": "firefox",
    "fire folks": "firefox",
    "fire folk": "firefox",
    "faierfox": "firefox",
    "faier fox": "firefox",
    "fayerfox": "firefox",
    "fayer fox": "firefox",
    "google chrome": "google-chrome",
    "chrome": "google-chrome",
    "crom": "google-chrome",
    "chromium": "chromium",
    # Terminal
    "terminal": "kitty",
    "consola": "kitty",
    "kitty": "kitty",
    "konsole": "konsole",
}

# ── Sistema prompt del LLM ───────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres Jota, un asistente de voz local e inteligente para Linux.
Deduce la intencion del usuario incluso si la voz tiene errores foneticos.
Responde siempre de forma breve, concisa y sin emojis.

Catálogo estricto de herramientas disponibles:
- screenshot(): Captura y muestra la pantalla del PC ("muestrame la pantalla del pc").
- switch_workspace(target=N): Cambia de escritorio ("pasa al escritorio 3").
- move_to_workspace(target=N): Mueve la ventana activa ("mueve la ventana al 3").
- open_app(name='...'): Abre aplicacion (ej: 'firefox' ante 'fire folks', 'kitty', 'dolphin').
- volume_control(action='up'|'down'|'mute'): Sube, baja o silencia el audio.
- media_control(action='play'|'pause'|'next'|'previous'): Control multimedia.
- web_search(query='...'): Busca en la web.
- phone_control(action='ring'|'status'|'torch'|'silent'|'open_url', value=...): Control movil.
- lock_pc(): Bloquea la pantalla del PC.
- system_power(action='suspend'|'reboot'|'shutdown'): Control de energia del equipo.
- close_active_window(): Cierra la ventana activa.
- pc_summary(): Consulta estado del PC (CPU, RAM, disco).
- send_notification(title='...', message='...'): Notificacion de escritorio.
- get_weather(city='...'): Clima de una ciudad (ej: 'Albacete').
- manage_notes(action='add'|'list'|'clear', text='...'): Gestiona notas.
- set_timer(seconds=N, label='...'): Inicia un temporizador.
- get_current_time(mode='time'|'date'|'full'): Consulta hora o fecha del sistema.

REGLAS CRÍTICAS:
1. SOLO puedes llamar a herramientas del catalogo. No inventes herramientas inexistentes.
2. Reanudar musica/audio: usa SIEMPRE TOOL: media_control(action='play'). JAMAS uses system_power.
3. Reiniciar o apagar: JAMAS apagues o reinicies sin confirmacion previa. Pregunta primero.
4. Si el usuario pide ver la pantalla del PC, usa TOOL: screenshot().
5. Si el usuario pide pasar de escritorio, usa TOOL: switch_workspace(target=N).
6. Si el usuario quiere ejecutar una accion, responde EXACTAMENTE en este formato:
TOOL: <nombre>(<parametros>)
<mensaje breve para decir en voz alta>
7. Si el usuario hace una pregunta general conversacional, responde breve y sin TOOL.

Ejemplos:
Usuario: reanuda la reproduccion
TOOL: media_control(action='play')
Reanudando la reproduccion.

Usuario: reinicia el equipo
¿Estas seguro de que deseas reiniciar el equipo? Di "si, confirma" para proceder.

Usuario: habla terminal
TOOL: open_app(name='terminal')
Abriendo la terminal.

Usuario: abre el explorador de archivos
TOOL: open_app(name='dolphin')
Abriendo el explorador de archivos.

Usuario: sube el volumen
TOOL: volume_control(action='up')
Subiendo el volumen.

Usuario: captura de pantalla
TOOL: screenshot()
Haciendo captura de pantalla.

Usuario: muestrame la pantalla del pc
TOOL: screenshot()
Aqui tienes la pantalla del PC.

Usuario: ver la pantalla del pc
TOOL: screenshot()
Aqui tienes la pantalla del PC.

Usuario: pasa al escritorio 3
TOOL: switch_workspace(target=3)
Cambiando al escritorio 3.

Usuario: pasad al escritorio 3
TOOL: switch_workspace(target=3)
Cambiando al escritorio 3.

Usuario: mueve la ventana al escritorio 3
TOOL: move_to_workspace(target=3)
Moviendo la ventana al escritorio 3.

Usuario: que tiempo hace hoy una albacete
TOOL: get_weather(city='Albacete')
Consultando el tiempo en Albacete.

Usuario: que tiempo hace en Madrid
TOOL: get_weather(city='Madrid')
Consultando el tiempo en Madrid.

Usuario: cuanta bateria le queda al movil
TOOL: phone_control(action='status')
Consultando el estado de tu telefono.

Usuario: bloquea el pc
TOOL: lock_pc()
Bloqueando el PC.

Usuario: que hora es
TOOL: get_current_time(mode='time')
Son las 14:45.

Usuario: que dia es hoy
TOOL: get_current_time(mode='date')
Hoy es domingo, 4 de octubre de 2026.

Usuario: como esta el pc
TOOL: pc_summary()
Consultando el estado del equipo.

Usuario: hola como estas
Hola, estoy listo para ayudarte."""

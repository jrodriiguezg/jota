"""
Configuración central de Jota.
Edita aquí las rutas a los modelos y preferencias.
"""

import os
import shutil
from pathlib import Path

# ── Rutas de modelos ─────────────────────────────────────────────────────────

# Directorio raíz donde están los modelos
MODELS_DIR = Path(
    os.getenv("JOTA_MODELS_DIR", str(Path.home() / ".local" / "share" / "jota" / "models"))
)

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

# Motor STT: "auto", "whisper_cli", o "faster_whisper"
STT_ENGINE = os.getenv("JOTA_STT_ENGINE", "auto").lower()
FASTER_WHISPER_MODEL = os.getenv("JOTA_FASTER_WHISPER_MODEL", "base")
FASTER_WHISPER_COMPUTE_TYPE = os.getenv("JOTA_FASTER_WHISPER_COMPUTE", "int8")

# LLM: seleccion del modelo optimizado para consumo ligero y baja latencia
def _resolve_llm_model() -> Path:
    env_model = os.getenv("JOTA_LLM_MODEL")
    if env_model and Path(env_model).is_file():
        return Path(env_model)

    qwen_dir = MODELS_DIR / "qwen"
    if qwen_dir.exists():
        profile = os.getenv("JOTA_LLM_PROFILE", "lightweight").lower()
        if profile in ("light", "lightweight", "fast"):
            # Priorizar modelos ligeros de bajo consumo y respuesta rapida (<1s)
            for preferred in (
                "qwen2.5-1.5b-instruct-q4_k_m.gguf",
                "qwen2.5-0.5b-instruct-q4_k_m.gguf",
                "Qwen3-0.6B-Q8_0.gguf",
            ):
                candidate = qwen_dir / preferred
                if candidate.is_file():
                    return candidate

        # Perfil quality: ordenar por tamano descendente
        ggufs = list(qwen_dir.glob("*.gguf"))
        if ggufs:
            ggufs.sort(key=lambda p: p.stat().st_size, reverse=(profile in ("quality", "heavy")))
            return ggufs[0]

    return MODELS_DIR / "qwen" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"



LLM_MODEL = _resolve_llm_model()
# Contexto optimizado para asistente de voz y catalogo (4096 tokens)
LLM_N_CTX = int(os.getenv("JOTA_LLM_CTX", "4096"))
LLM_N_GPU_LAYERS = int(os.getenv("JOTA_LLM_GPU_LAYERS", "0"))
# Limitar hilos para evitar saturar la CPU al 99%
LLM_THREADS = int(os.getenv("JOTA_LLM_THREADS", "4"))

# Backend LLM nativo autonomo (100% local via llama-cpp-python, sin Ollama)
LLM_BACKEND = "llama_cpp"


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

# ── Wake word y Escucha Manos Libres ─────────────────────────────────────────

# Palabras que activan el asistente (en minusculas).
# Se eliminan del inicio de la frase antes de pasar al LLM.
WAKE_WORDS = ["jota", "hota", "j"]  # Whisper transcribe frecuentemente 'J' a secas

# En modo push-to-talk (tecla Copilot), no es necesario decir la wake word.
# La wake word se reserva para activacion manos libres (sin teclas).
REQUIRE_WAKE_WORD = False

# Escucha continua en segundo plano (desactivada por defecto para push-to-talk)
HANDSFREE_ENABLED = os.getenv("JOTA_HANDSFREE", "false").lower() in ("true", "1", "yes")
# Umbral RMS de deteccion de voz (VAD) para microfono
VAD_THRESHOLD = float(os.getenv("JOTA_VAD_THRESHOLD", "0.015"))
# Segundos de silencio para delimitar el fin de una frase hablada
VAD_SILENCE_TIMEOUT = float(os.getenv("JOTA_VAD_SILENCE", "0.65"))
# Segundos de audio previo a conservar para no cortar el inicio de palabra
VAD_PRE_SPEECH_DURATION = float(os.getenv("JOTA_VAD_PRE_SPEECH", "0.4"))
# Duracion maxima de una orden de voz continua en segundos
VAD_MAX_DURATION = float(os.getenv("JOTA_VAD_MAX_DURATION", "8.0"))

# ── Audio ────────────────────────────────────────────────────────────────────

AUDIO_SAMPLE_RATE = 16000   # Hz (whisper.cpp espera 16kHz)
AUDIO_CHANNELS = 1
AUDIO_DTYPE = "int16"
# Duracion maxima de grabacion en segundos (por si no suelta la tecla)
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

ORB_ENABLED = os.getenv("JOTA_ORB_ENABLED", "true").lower() in ("true", "1", "yes")
ORB_SIZE = 140
ORB_CORNER = "bottom_right"  # "bottom_right", "bottom_left", "top_right", "top_left"
ORB_MARGIN_X = 28
ORB_MARGIN_Y = 28
ORB_FPS = 60
ORB_SOCKET_PATH = Path("/tmp/jota_orb.sock")
# Ocultar completamente el orbe cuando este en reposo (idle) para que sea sigiloso
ORB_AUTO_HIDE_IDLE = os.getenv("JOTA_ORB_AUTO_HIDE", "true").lower() in ("true", "1", "yes")

# Bandeja del sistema (System Tray / AppIndicator)
TRAY_ENABLED = os.getenv("JOTA_TRAY", "true").lower() in ("true", "1", "yes")

# ── Herramientas (Fase 2) ────────────────────────────────────────────────────

# Navidrome / Subsonic (Musica inteligente y Handoff)
NAVIDROME_URL = os.getenv("NAVIDROME_URL", "http://localhost:4533")
NAVIDROME_USER = os.getenv("NAVIDROME_USER", "admin")
NAVIDROME_SALT = os.getenv("NAVIDROME_SALT", "")
NAVIDROME_TOKEN = os.getenv("NAVIDROME_TOKEN", "")

# Music Assistant (Sincronizacion y Handoff entre PC y Movil)
MUSIC_ASSISTANT_URL = os.getenv("MUSIC_ASSISTANT_URL", "http://localhost:8095")
MUSIC_ASSISTANT_TOKEN = os.getenv("MUSIC_ASSISTANT_TOKEN", "")
MUSIC_ASSISTANT_CONFIG = Path.home() / ".config" / "jota" / "mass.json"

# Rutas de escenas y rutinas
SCENES_FILE = Path.home() / ".config" / "jota" / "scenes.yaml"

# Alias y catalogo de dispositivos multi-pantalla y multimedia
DEVICES = {
    "tele": {"name": "Android TV Salón", "type": "cast", "adb": "192.168.1.50:5555"},
    "television": {"name": "Android TV Salón", "type": "cast", "adb": "192.168.1.50:5555"},
    "tv": {"name": "Android TV Salón", "type": "cast", "adb": "192.168.1.50:5555"},
    "salon": {"name": "Android TV Salón", "type": "cast", "adb": "192.168.1.50:5555"},
    "tablet": {"name": "Tablet", "type": "vnc", "host": "192.168.1.180"},
    "movil": {"name": "Teléfono", "type": "adb", "serial": os.getenv("JOTA_PHONE_SERIAL", "")},
    "telefono": {"name": "Teléfono", "type": "adb", "serial": os.getenv("JOTA_PHONE_SERIAL", "")},
}

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
    "reproductor de música": "org.jeffvli.feishin",
    "reproductor multimedia": "org.jeffvli.feishin",
    "reproductor de audio": "org.jeffvli.feishin",
    "reproductor": "org.jeffvli.feishin",
    "musica": "org.jeffvli.feishin",
    "música": "org.jeffvli.feishin",
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
Responde siempre breve, conciso y sin emojis.

Herramientas disponibles:
- screenshot(): Captura y muestra la pantalla del PC.
- switch_workspace(target=N): Cambia de escritorio (1-10).
- move_to_workspace(target=N): Mueve la ventana activa de escritorio.
- open_app(name='...'): Abre aplicacion ('musica', 'dolphin', 'firefox', 'terminal').
- volume_control(action='up'|'down'|'mute'|'set', level=N): Control de volumen.
- media_control(action='play'|'pause'|'next'|'previous'): Control multimedia.
- web_search(query='...'): Busca en la web.
- phone_control(action='ring'|'status'|'torch'|'silent'|'open_url', value=...): Control movil.
- lock_pc(): Bloquea la pantalla del PC.
- system_power(action='suspend'|'reboot'|'shutdown'): Energia del PC.
- close_window(app='...'): Cierra app o ventana activa.
- pc_summary(): Estado del PC (CPU, RAM, disco).
- get_pc_battery(): Bateria del PC.
- get_now_playing(): Cancion que esta sonando.
- send_notification(title='...', message='...'): Notificacion de escritorio.
- get_weather(city='...'): Clima de una ciudad.
- manage_notes(action='add'|'list'|'clear', text='...'): Notas.
- set_timer(seconds=N, label='...'): Temporizador.
- cancel_timer(): Cancela temporizador activo.
- get_current_time(mode='time'|'date'|'full'): Hora o fecha.
- check_package(name='...', check='version'|'installed'): Verifica paquete en sistema.
- analyze_screen(question='...'): Analiza la pantalla con vision.
- window_action(action='fullscreen'|'float'|'pin'|'center'): Manipula ventana activa.
- focus_app(name='...'): Enfoca ventana abierta.
- brightness_control(percent=N, action='set'|'up'|'down'): Brillo de pantalla.
- night_mode_control(action='on'|'off'|'toggle'): Filtro de luz azul.
- port_action(port=N, action='check'|'kill'): Consulta o libera puerto.
- container_action(action='list'|'stop'|'start', target='...'): Contenedores Docker/Podman.
- process_monitor(action='top_cpu'|'top_ram'): Procesos con mas consumo.
- kill_process(target='...'): Termina proceso.
- git_status(path='...'): Estado de Git.
- phone_send_screenshot(workspace=N): Envia captura al movil.
- phone_send_url(url='...'): Envia URL al movil.
- phone_send_file(target='...'): Envia archivo al movil.
- trigger_scene(name='...'): Activa escena ('modo_cine', 'modo_trabajo', 'buenas_noches').
- list_scenes(): Lista escenas configuradas.
- cast_media(target='tele'): Envia video o audio a la tele.
- cast_control(action='pause'|'resume'|'stop', target='tele'): Control en la tele.
- launch_tv_app(name='...', target='tele'): Abre app en la tele ('netflix', 'prime', 'youtube').
- cec_control(action='turn_on'|'turn_off'|'switch', target='tele'): HDMI-CEC de la tele.
- open_phone_screen(): Muestra la pantalla del movil en PC con scrcpy.
- tablet_display(action='start'|'stop'): Usa tablet como segunda pantalla con wayvnc.
- favorite_song(): Marca cancion como favorita en Navidrome.
- navidrome_play(query='...'): Reproduce musica con cola inteligente en Navidrome.
- media_handoff(target='movil'|'pc'): Transfiere la musica activa entre PC y movil.
- music_assistant_play(query='...', target='pc'|'movil'): Reproduce en Music Assistant.
- music_assistant_transfer(source='pc', target='movil'): Transfiere musica en Music Assistant.

Reglas:
1. Si vas a ejecutar una accion, responde EXACTAMENTE en este formato:
TOOL: <herramienta>(<args>)
<mensaje breve para decir en voz alta>
2. Si es una pregunta general o conversacion, responde brevemente sin TOOL.
3. Para reanudar musica usa SIEMPRE TOOL: media_control(action='play').
4. Para reiniciar o apagar pide confirmacion primero.

Ejemplos:
Usuario: pon la pantalla del movil
TOOL: open_phone_screen()
Mostrando la pantalla del movil en el escritorio.

Usuario: pasa la musica al movil
TOOL: music_assistant_transfer(source='pc', target='movil')
Transfiriendo la musica a tu movil.

Usuario: modo cine
TOOL: trigger_scene(name='modo_cine')
Activando modo cine.

Usuario: que contenedores estan corriendo
TOOL: container_action(action='list')
Consultando contenedores activos.

Usuario: hola como estas
Hola, estoy listo para ayudarte."""

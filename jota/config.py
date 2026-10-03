"""
Configuración central de Jota.
Edita aquí las rutas a los modelos y preferencias.
"""

import shutil
from pathlib import Path

# ── Rutas de modelos ─────────────────────────────────────────────────────────

# Directorio raíz donde están los modelos
MODELS_DIR = Path.home() / ".local" / "share" / "jota" / "models"

# Whisper: ruta al binario de whisper.cpp
# Nota: en versiones recientes el binario se llama whisper-cli (antes whisper-cpp)
WHISPER_BIN = Path("/usr/local/bin/whisper-cli")
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

# Parametros de muestreo recomendados oficialmente por Qwen3:
LLM_TEMPERATURE = 0.7
LLM_TOP_P = 0.8
LLM_TOP_K = 20
LLM_PRESENCE_PENALTY = 1.5

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

SYSTEM_PROMPT = """Eres Jota, un asistente de voz local para Linux conciso y util.
Responde siempre en espanol, de forma breve y directa.
No uses markdown, listas con asteriscos ni emojis: tus respuestas se leen en voz alta.

Solo usa una instruccion TOOL si el usuario te pide explicitamente una accion del sistema:
- Controlar volumen: TOOL: volume_control(action='up'|'down'|'mute')
- Controlar musica: TOOL: media_control(action='play'|'pause'|'play_pause'|'next'|'previous')
- Capturar pantalla: TOOL: screenshot()
- Abrir programa: TOOL: open_app(name='...')
- Buscar en internet: TOOL: web_search(query='...')

Si el usuario te hace una pregunta, saludo o conversacion general,
responde con texto normal sin TOOL.
Maximo 2 frases por respuesta."""

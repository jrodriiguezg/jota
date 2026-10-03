"""STT: transcripción de audio usando el binario de whisper.cpp."""

import logging
import re
import subprocess
from pathlib import Path

from jota.config import WAKE_WORDS, WHISPER_BIN, WHISPER_LANG, WHISPER_MODEL

logger = logging.getLogger(__name__)


def transcribe(audio_path: Path) -> str | None:
    """
    Llama a whisper.cpp para transcribir el archivo de audio dado.
    Devuelve el texto transcrito (en minúsculas, sin signos de puntuación extra)
    o None si hubo un error.
    """
    if not WHISPER_BIN.exists():
        raise FileNotFoundError(
            f"Binario de whisper-cli no encontrado en {WHISPER_BIN}.\n"
            "Instálalo con:\n"
            "  sudo install -m 755 /tmp/whisper-build/build/bin/whisper-cli /usr/local/bin/whisper-cli"
        )
    if not WHISPER_MODEL.exists():
        raise FileNotFoundError(
            f"Modelo de whisper no encontrado en {WHISPER_MODEL}.\n"
            "Descárgalo desde https://huggingface.co/ggerganov/whisper.cpp"
        )

    cmd = [
        str(WHISPER_BIN),
        "-m", str(WHISPER_MODEL),
        "-f", str(audio_path),
        "-l", WHISPER_LANG,
        "--no-timestamps",
        "-otxt",  # salida a archivo .txt
        "-of", str(audio_path.with_suffix("")),  # prefijo del archivo de salida
    ]

    logger.debug("Ejecutando whisper: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        logger.error("whisper.cpp tardó demasiado (timeout).")
        return None

    if result.returncode != 0:
        logger.error("whisper.cpp falló: %s", result.stderr)
        return None

    # whisper -otxt escribe <audio_path>.txt
    txt_file = audio_path.with_suffix(".txt")
    if txt_file.exists():
        text = txt_file.read_text(encoding="utf-8").strip()
        txt_file.unlink(missing_ok=True)  # limpiamos
        logger.info("Transcripción: %r", text)
        return text

    # fallback: parsear stdout
    text = result.stdout.strip()
    if text:
        return text

    logger.warning("whisper.cpp no devolvió texto.")
    return None


def strip_wake_word(text: str) -> str | None:
    """
    Elimina el wake word del inicio de la frase.
    Ejemplos:
        "Jota, ¿cómo estás?"   → "¿cómo estás?"
        "¡Jota! qué hora es"   → "qué hora es"
        "Hota qué hora es"      → "qué hora es"
        "Cómo estás"            → None  (sin wake word detectado)

    Devuelve el texto limpio o None si no se detectó ningún wake word.
    """
    cleaned_start = re.sub(r"^[\s¡¿\"']+", "", text)
    normalized = cleaned_start.strip().lower()

    # Ordenar por longitud descendente para que 'jota' tenga prioridad sobre 'j'
    sorted_words = sorted(WAKE_WORDS, key=len, reverse=True)

    for word in sorted_words:
        # Exigir delimitador de palabra (espacio, puntuación o fin de cadena)
        pattern = rf"^{re.escape(word)}(?:[\s,\.!¿?¡\"':;\-]+|$)"
        match = re.match(pattern, normalized)
        if match:
            cleaned = cleaned_start[match.end():].strip()
            # Quitar separadores tras el wake word (comas, espacios, exclamacion, etc.) sin borrar el signo de interrogacion
            cleaned = re.sub(r"^[\s,\-:;!\.]+", "", cleaned)
            logger.debug("Wake word '%s' detectado. Frase limpia: %r", word, cleaned)
            return cleaned if cleaned else None

    logger.debug("No se detectó wake word en: %r", text)
    return None

"""STT: transcripcion de audio usando el binario nativo de whisper.cpp (whisper-cli)."""

import logging
import os
import re
import subprocess
from pathlib import Path

from jota.config import WAKE_WORDS, WHISPER_BIN, WHISPER_LANG, WHISPER_MODEL

logger = logging.getLogger(__name__)


def transcribe(audio_path: Path) -> str | None:
    """
    Llama a whisper.cpp para transcribir el archivo de audio dado.
    Devuelve el texto transcrito o None si hubo un error.
    """
    if not WHISPER_BIN.exists():
        raise FileNotFoundError(
            f"Binario de whisper-cli no encontrado en {WHISPER_BIN}.\n"
            "Ejecuta bash setup.sh para compilarlo e instalarlo automaticamente."
        )
    if not WHISPER_MODEL.exists():
        raise FileNotFoundError(
            f"Modelo de whisper no encontrado en {WHISPER_MODEL}.\n"
            "Descargalo ejecutando bash setup.sh"
        )

    # Optimizacion de hilos de CPU para transcribir mas rapido
    threads = str(min(8, os.cpu_count() or 4))
    output_prefix = audio_path.with_suffix("")
    txt_file = audio_path.with_suffix(".txt")

    # Limpiar archivo previo si existia para no leer transcripciones antiguas
    txt_file.unlink(missing_ok=True)

    cmd = [
        str(WHISPER_BIN),
        "-m", str(WHISPER_MODEL),
        "-f", str(audio_path),
        "-l", WHISPER_LANG,
        "-t", threads,
        "--no-timestamps",
        "-otxt",
        "-of", str(output_prefix),
    ]

    logger.debug("Ejecutando whisper: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            logger.error("whisper.cpp fallo (code %s): %s", result.returncode, result.stderr)
            return None

        # whisper -otxt escribe <audio_path>.txt
        if txt_file.exists():
            text = txt_file.read_text(encoding="utf-8").strip()
            if text:
                logger.info("Transcripcion: %r", text)
                return text

        # fallback: parsear stdout si el archivo txt no se genero
        text = result.stdout.strip()
        if text:
            return text

        logger.warning("whisper.cpp no devolvio texto.")
        return None

    except subprocess.TimeoutExpired:
        logger.error("whisper.cpp tardo demasiado (timeout).")
        return None
    except Exception as e:
        logger.error("Error inesperado en transcripcion: %s", e)
        return None
    finally:
        txt_file.unlink(missing_ok=True)


def strip_wake_word(text: str) -> str | None:
    """
    Elimina el wake word del inicio de la frase.
    Ejemplos:
        "Jota, ¿como estas?"   -> "como estas?"
        "J, ¿como estas?"      -> "como estas?"
        "¡Jota! que hora es"   -> "que hora es"
        "Hota que hora es"     -> "que hora es"
        "Como estas"           -> None  (sin wake word detectado)

    Devuelve el texto limpio o None si no se detecto ningun wake word.
    """
    cleaned_start = re.sub(r"^[\s¡¿\"']+", "", text)
    normalized = cleaned_start.strip().lower()

    # Ordenar por longitud descendente para que 'jota' tenga prioridad sobre 'j'
    sorted_words = sorted(WAKE_WORDS, key=len, reverse=True)

    for word in sorted_words:
        # Exigir delimitador de palabra (espacio, puntuacion o fin de cadena)
        pattern = rf"^{re.escape(word)}(?:[\s,\.!¿?¡\"':;\-]+|$)"
        match = re.match(pattern, normalized)
        if match:
            cleaned = cleaned_start[match.end():].strip()
            cleaned = re.sub(r"^[\s,\-:;!\.]+", "", cleaned)
            # Limpiar signo de apertura residual si quedo suelto
            cleaned = re.sub(r"^[¡¿]+", "", cleaned).strip()
            logger.debug("Wake word '%s' detectado. Frase limpia: %r", word, cleaned)
            return cleaned if cleaned else None

    logger.debug("No se detecto wake word en: %r", text)
    return None

"""STT: transcripcion de audio usando whisper.cpp (whisper-cli) o faster-whisper."""

import logging
import os
import re
import subprocess
from pathlib import Path

from jota.config import (
    FASTER_WHISPER_COMPUTE_TYPE,
    FASTER_WHISPER_MODEL,
    REQUIRE_WAKE_WORD,
    STT_ENGINE,
    WAKE_WORDS,
    WHISPER_BIN,
    WHISPER_LANG,
    WHISPER_MODEL,
)

logger = logging.getLogger(__name__)

_faster_whisper_model = None


def _get_faster_whisper_model():
    global _faster_whisper_model
    if _faster_whisper_model is None:
        try:
            from faster_whisper import WhisperModel

            threads = min(8, os.cpu_count() or 4)
            logger.info(
                "Cargando faster-whisper (modelo=%s, compute=%s, threads=%d)...",
                FASTER_WHISPER_MODEL,
                FASTER_WHISPER_COMPUTE_TYPE,
                threads,
            )
            _faster_whisper_model = WhisperModel(
                FASTER_WHISPER_MODEL,
                device="cpu",
                compute_type=FASTER_WHISPER_COMPUTE_TYPE,
                cpu_threads=threads,
            )
        except Exception as e:
            logger.error("No se pudo cargar faster-whisper: %s", e)
            return None
    return _faster_whisper_model


def _transcribe_faster_whisper(audio_path: Path) -> str | None:
    model = _get_faster_whisper_model()
    if model is None:
        return None
    try:
        segments, _ = model.transcribe(
            str(audio_path),
            language=WHISPER_LANG,
            beam_size=1,
            vad_filter=True,
        )
        parts = [seg.text.strip() for seg in segments if seg.text.strip()]
        raw_text = " ".join(parts).strip()
        if raw_text:
            if re.match(r"^\[[\w\s.-]+\]$", raw_text) or re.match(r"^\([\w\s.-]+\)$", raw_text):
                logger.debug("Artefacto de silencio descartado: %r", raw_text)
                return None
            logger.info("Transcripcion (faster-whisper): %r", raw_text)
            return raw_text
        return None
    except Exception as e:
        logger.error("Error en faster-whisper: %s", e)
        return None


def _transcribe_whisper_cli(audio_path: Path) -> str | None:
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
        raw_text = ""
        if txt_file.exists():
            raw_text = txt_file.read_text(encoding="utf-8").strip()
        elif result.stdout.strip():
            raw_text = result.stdout.strip()

        if raw_text:
            # Descartar alucinaciones de whisper sobre silencio (ej. [SILENCIO], [Puerto], (ruido))
            if re.match(r"^\[[\w\s.-]+\]$", raw_text) or re.match(r"^\([\w\s.-]+\)$", raw_text):
                logger.debug("Artefacto de silencio descartado: %r", raw_text)
                return None
            logger.info("Transcripcion: %r", raw_text)
            return raw_text

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


def transcribe(audio_path: Path) -> str | None:
    """
    Transcribe el audio usando el motor configurado (faster-whisper o whisper-cli).
    Devuelve el texto transcrito o None si hubo un error.
    """
    if STT_ENGINE == "faster_whisper":
        return _transcribe_faster_whisper(audio_path)

    if STT_ENGINE == "whisper_cli":
        return _transcribe_whisper_cli(audio_path)

    # Modo automatico: usar faster-whisper si whisper-cli no esta instalado
    if not WHISPER_BIN.exists():
        result = _transcribe_faster_whisper(audio_path)
        if result is not None:
            return result

    return _transcribe_whisper_cli(audio_path)


def extract_wake_word(text: str) -> tuple[bool, str]:
    """
    Comprueba si el texto comienza por un wake word ("jota", "hota", "j", etc.).
    Devuelve (True, comando_limpio) si el wake word esta presente.
    Si solo se pronuncio el wake word (ej. "Jota"), devuelve (True, "").
    Si no se detecto el wake word, devuelve (False, text).
    """
    cleaned_start = re.sub(r"^[\s¡¿\"']+", "", text).strip()
    if not cleaned_start:
        return False, ""

    normalized = cleaned_start.lower()
    sorted_words = sorted(WAKE_WORDS, key=len, reverse=True)

    for word in sorted_words:
        pattern = rf"^{re.escape(word)}(?:[\s,\.!¿?¡\"':;\-]+|$)"
        match = re.match(pattern, normalized)
        if match:
            cleaned = cleaned_start[match.end():].strip()
            cleaned = re.sub(r"^[\s,\-:;!\.]+", "", cleaned)
            cleaned = re.sub(r"^[¡¿]+", "", cleaned).strip()
            logger.debug("Wake word '%s' detectado en: %r", word, text)
            return True, cleaned

    return False, cleaned_start


def strip_wake_word(text: str, require_wake_word: bool = REQUIRE_WAKE_WORD) -> str | None:
    """
    Elimina el wake word del inicio de la frase si esta presente.
    Si require_wake_word es False (modo push-to-talk por defecto):
        - Si tiene wake word, lo retira y devuelve el resto.
        - Si no tiene wake word, devuelve la frase limpia de signos iniciales.
    Si require_wake_word es True (modo manos libres):
        - Devuelve None si no se detecto ningun wake word o la frase quedo vacia.
    """
    has_wake, command = extract_wake_word(text)
    if has_wake:
        return command if command else None
    if require_wake_word:
        logger.debug("No se detecto wake word requerido en: %r", text)
        return None
    logger.debug("Procesando directamente en modo push-to-talk: %r", command)
    return command if command else None

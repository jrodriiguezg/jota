"""TTS: sintesis de voz con piper-tts y reproduccion por altavoces."""

import logging
import subprocess
import tempfile
from pathlib import Path

import sounddevice as sd
import soundfile as sf

from jota.config import PIPER_BIN, PIPER_MODEL

logger = logging.getLogger(__name__)


def synthesize_to_file(text: str, output_path: Path) -> bool:
    """
    Sintetiza texto a un archivo WAV usando piper-tts.
    Devuelve True si el archivo se genero exitosamente.
    """
    if not text or not text.strip():
        return False

    if not PIPER_BIN.exists():
        logger.error("Binario de piper no encontrado en %s", PIPER_BIN)
        return False
    if not PIPER_MODEL.exists():
        logger.error("Modelo de voz piper no encontrado en %s", PIPER_MODEL)
        return False

    logger.debug("TTS sintesis a archivo %s: %r", output_path, text)
    try:
        cmd = [
            str(PIPER_BIN),
            "--model", str(PIPER_MODEL),
            "--output_file", str(output_path),
        ]
        result = subprocess.run(
            cmd,
            input=text,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.error("piper-tts fallo: %s", result.stderr)
            return False

        if output_path.exists() and output_path.stat().st_size > 44:
            return True

        logger.warning("piper-tts genero un archivo vacio.")
        return False

    except subprocess.TimeoutExpired:
        logger.error("piper-tts tardo demasiado (timeout).")
        return False
    except Exception as e:
        logger.error("Error durante la sintesis TTS: %s", e)
        return False


def speak(text: str) -> None:
    """
    Sintetiza el texto con piper-tts y lo reproduce por los altavoces.
    Bloquea hasta que el audio termine de reproducirse.
    """
    if not text or not text.strip():
        return

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        success = synthesize_to_file(text, tmp_path)
        if success:
            _play_wav(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _play_wav(path: Path) -> None:
    """Reproduce un archivo WAV por los altavoces del sistema."""
    try:
        data, samplerate = sf.read(str(path), dtype="float32")
        logger.debug("Reproduciendo respuesta (%.2fs)...", len(data) / samplerate)
        sd.play(data, samplerate)
        sd.wait()
    except Exception as e:
        logger.error("Error reproduciendo audio por altavoces: %s", e)

"""TTS: síntesis de voz con piper-tts."""

import logging
import subprocess
import tempfile
from pathlib import Path

import sounddevice as sd
import soundfile as sf

from jota.config import AUDIO_SAMPLE_RATE, PIPER_BIN, PIPER_MODEL

logger = logging.getLogger(__name__)


def speak(text: str) -> None:
    """
    Sintetiza el texto con piper-tts y lo reproduce por los altavoces.
    Bloquea hasta que el audio termine de reproducirse.
    """
    if not PIPER_BIN.exists():
        raise FileNotFoundError(
            f"Binario de piper no encontrado en {PIPER_BIN}.\n"
            "Instálalo con: pip install piper-tts  o descarga el binario de https://github.com/rhasspy/piper"
        )
    if not PIPER_MODEL.exists():
        raise FileNotFoundError(
            f"Modelo de piper no encontrado en {PIPER_MODEL}.\n"
            "Descarga un modelo en español desde https://huggingface.co/rhasspy/piper-voices"
        )

    logger.debug("TTS: %r", text)

    # Piper lee de stdin y escribe WAV a stdout
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        cmd = [
            str(PIPER_BIN),
            "--model", str(PIPER_MODEL),
            "--output_file", str(tmp_path),
        ]
        result = subprocess.run(
            cmd,
            input=text,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error("piper-tts falló: %s", result.stderr)
            return

        _play_wav(tmp_path)

    except subprocess.TimeoutExpired:
        logger.error("piper-tts tardó demasiado.")
    finally:
        tmp_path.unlink(missing_ok=True)


def _play_wav(path: Path) -> None:
    """Reproduce un archivo WAV por los altavoces del sistema."""
    data, samplerate = sf.read(str(path), dtype="float32")
    logger.debug("Reproduciendo respuesta (%.2fs)...", len(data) / samplerate)
    sd.play(data, samplerate)
    sd.wait()

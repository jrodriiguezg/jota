"""TTS: sintesis de voz con piper-tts y reproduccion por altavoces."""

import logging
import subprocess
import tempfile
from pathlib import Path

import sounddevice as sd
import soundfile as sf

from jota.config import PIPER_BIN, PIPER_MODEL

logger = logging.getLogger(__name__)


def speak(text: str) -> None:
    """
    Sintetiza el texto con piper-tts y lo reproduce por los altavoces.
    Bloquea hasta que el audio termine de reproducirse.
    """
    if not text or not text.strip():
        return

    if not PIPER_BIN.exists():
        raise FileNotFoundError(
            f"Binario de piper no encontrado en {PIPER_BIN}.\n"
            "Ejecuta bash setup.sh para instalarlo en tu entorno."
        )
    if not PIPER_MODEL.exists():
        raise FileNotFoundError(
            f"Modelo de voz piper no encontrado en {PIPER_MODEL}.\n"
            "Ejecuta bash setup.sh para descargarlo."
        )

    logger.debug("TTS: %r", text)

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
            logger.error("piper-tts fallo: %s", result.stderr)
            return

        if tmp_path.exists() and tmp_path.stat().st_size > 44:  # 44 bytes es solo la cabecera WAV
            _play_wav(tmp_path)
        else:
            logger.warning("piper-tts genero un archivo de audio vacio.")

    except subprocess.TimeoutExpired:
        logger.error("piper-tts tardo demasiado (timeout).")
    except Exception as e:
        logger.error("Error durante la sintesis TTS: %s", e)
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

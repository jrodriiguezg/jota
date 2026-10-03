"""Módulo de audio: grabación desde micrófono mientras se mantiene pulsada la tecla."""

import logging
import threading
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

from jota.config import AUDIO_CHANNELS, AUDIO_DTYPE, AUDIO_MAX_DURATION, AUDIO_SAMPLE_RATE, AUDIO_TMP_FILE

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Graba audio del micrófono mientras se llame a start() hasta stop()."""

    def __init__(self):
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._recording = False

    def start(self) -> None:
        """Inicia la grabación."""
        self._frames = []
        self._recording = True
        logger.debug("Iniciando grabación de audio...")

        self._stream = sd.InputStream(
            samplerate=AUDIO_SAMPLE_RATE,
            channels=AUDIO_CHANNELS,
            dtype=AUDIO_DTYPE,
            callback=self._callback,
            blocksize=1024,
        )
        self._stream.start()

    def _callback(self, indata: np.ndarray, frames: int, time, status) -> None:
        if status:
            logger.warning("Estado del stream de audio: %s", status)
        if self._recording:
            with self._lock:
                self._frames.append(indata.copy())

    def stop(self) -> Path | None:
        """
        Detiene la grabación y guarda el audio en un WAV temporal.
        Devuelve la ruta del archivo o None si no se grabó nada.
        """
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            frames = self._frames.copy()

        if not frames:
            logger.warning("No se capturó audio.")
            return None

        audio = np.concatenate(frames, axis=0)
        duration = len(audio) / AUDIO_SAMPLE_RATE
        logger.debug("Audio capturado: %.2f segundos", duration)

        if duration < 0.3:
            logger.info("Audio demasiado corto (%.2fs), ignorando.", duration)
            return None

        _save_wav(audio, AUDIO_TMP_FILE)
        return AUDIO_TMP_FILE


def _save_wav(audio: np.ndarray, path: Path) -> None:
    """Guarda un array de numpy como archivo WAV mono 16-bit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(AUDIO_CHANNELS)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(AUDIO_SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    logger.debug("Audio guardado en %s", path)

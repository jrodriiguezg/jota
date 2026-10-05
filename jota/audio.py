"""Modulo de audio: grabacion desde microfono con limites y gestion segura de recursos."""

import logging
import threading
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

from jota.config import (
    AUDIO_CHANNELS,
    AUDIO_DTYPE,
    AUDIO_MAX_DURATION,
    AUDIO_SAMPLE_RATE,
    AUDIO_TMP_FILE,
)

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Graba audio del microfono mientras se llame a start() hasta stop()."""

    def __init__(self, level_callback=None):
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._recording = False
        self._max_blocks = int(AUDIO_MAX_DURATION * AUDIO_SAMPLE_RATE / 1024)
        self.level_callback = level_callback
        self.last_peak: float = 0.0

    @property
    def is_recording(self) -> bool:
        """Devuelve True si el grabador esta capturando audio actualmente."""
        with self._lock:
            return self._recording

    def start(self) -> None:
        """Inicia la grabacion si no estaba ya activa."""
        with self._lock:
            if self._recording:
                logger.debug("Grabacion ya en curso, ignorando nuevo start().")
                return

            self._frames = []
            self._recording = True
            self.last_peak = 0.0

        logger.debug("Iniciando grabacion de audio...")
        try:
            self._stream = sd.InputStream(
                samplerate=AUDIO_SAMPLE_RATE,
                channels=AUDIO_CHANNELS,
                dtype=AUDIO_DTYPE,
                callback=self._callback,
                blocksize=1024,
            )
            self._stream.start()
        except Exception as e:
            with self._lock:
                self._recording = False
            logger.error("No se pudo iniciar el stream de audio del microfono: %s", e)

    def _callback(self, indata: np.ndarray, frames: int, time, status) -> None:
        if status:
            logger.warning("Aviso en stream de audio: %s", status)

        peak = float(np.max(np.abs(indata))) / 32768.0
        self.last_peak = peak
        cb = self.level_callback
        with self._lock:
            if self._recording:
                self._frames.append(indata.copy())
                # Limite maximo de seguridad para evitar consumo infinito de RAM
                if len(self._frames) >= self._max_blocks:
                    logger.info("Limite de duracion de audio alcanzado (%ss).", AUDIO_MAX_DURATION)
                    self._recording = False

        if cb and self._recording:
            try:
                # Normalizar rms / pico del buffer int16 (-32768 a 32767)
                cb(min(1.0, peak * 2.8))
            except Exception:
                pass

    def stop(self) -> Path | None:
        """
        Detiene la grabacion y guarda el audio en un WAV temporal seguro.
        Devuelve la ruta del archivo o None si no se grabo nada valido.
        """
        with self._lock:
            if not self._recording and not self._frames:
                return None
            self._recording = False

        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.warning("Error cerrando stream de audio: %s", e)
            finally:
                self._stream = None

        with self._lock:
            frames = self._frames.copy()
            self._frames.clear()

        if not frames:
            logger.warning("No se capturo audio.")
            return None

        audio = np.concatenate(frames, axis=0)
        duration = len(audio) / AUDIO_SAMPLE_RATE
        logger.debug("Audio capturado: %.2f segundos", duration)

        if duration < 0.3:
            logger.info("Audio demasiado corto (%.2fs), ignorando.", duration)
            return None

        try:
            _save_wav(audio, AUDIO_TMP_FILE)
            return AUDIO_TMP_FILE
        except Exception as e:
            logger.error("Error guardando archivo WAV de audio: %s", e)
            return None


def _save_wav(audio: np.ndarray, path: Path) -> None:
    """Guarda un array de numpy como archivo WAV mono 16-bit en ruta segura."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(AUDIO_CHANNELS)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(AUDIO_SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    logger.debug("Audio guardado en %s", path)

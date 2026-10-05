"""
Deteccion continua de wake word en segundo plano (manos libres).
Monitorea el microfono en tiempo real con Voice Activity Detection (VAD) de ultra-bajo
consumo CPU (<0.5%) y activa Jota solo cuando se pronuncia la palabra clave ("Jota").
"""

import logging
import queue
import threading
import uuid
from collections import deque
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from jota import stt
from jota.audio import _save_wav
from jota.config import (
    AUDIO_CHANNELS,
    AUDIO_DTYPE,
    AUDIO_SAMPLE_RATE,
    AUDIO_TMP_DIR,
    VAD_MAX_DURATION,
    VAD_PRE_SPEECH_DURATION,
    VAD_SILENCE_TIMEOUT,
    VAD_THRESHOLD,
)

logger = logging.getLogger(__name__)


class WakeWordListener:
    """
    Listener continuo de microfono con detector VAD (Voice Activity Detection).
    Acumula fragmentos cuando detecta voz y los transcribe con whisper.
    Si se detecta la wake word ('Jota'), invoca el callback configurado.
    """

    def __init__(
        self,
        on_wake: Callable[[str], None],
        level_callback: Callable[[float], None] | None = None,
        vad_threshold: float = VAD_THRESHOLD,
        silence_timeout: float = VAD_SILENCE_TIMEOUT,
        sample_rate: int = AUDIO_SAMPLE_RATE,
    ):
        self.on_wake = on_wake
        self.level_callback = level_callback
        self.vad_threshold = vad_threshold
        self.silence_timeout = silence_timeout
        self.sample_rate = sample_rate

        self._blocksize = 1024
        self._pre_speech_blocks = max(
            1, int(VAD_PRE_SPEECH_DURATION * sample_rate / self._blocksize)
        )
        self._max_speech_blocks = int(VAD_MAX_DURATION * sample_rate / self._blocksize)
        self._silence_blocks_needed = max(1, int(silence_timeout * sample_rate / self._blocksize))

        self._pre_buffer: deque[np.ndarray] = deque(maxlen=self._pre_speech_blocks)
        self._speech_frames: list[np.ndarray] = []
        self._in_speech = False
        self._silence_blocks = 0
        self._consecutive_speech_blocks = 0

        self._queue: queue.Queue[list[np.ndarray]] = queue.Queue(maxsize=10)
        self._paused = False
        self._running = False
        self._stream: sd.InputStream | None = None
        self._worker_thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        """Devuelve True si el listener esta activo."""
        return self._running

    @property
    def is_paused(self) -> bool:
        """Devuelve True si el listener esta temporalmente pausado."""
        return self._paused

    def start(self) -> None:
        """Inicia el worker thread y el stream de microfono."""
        if self._running:
            return

        self._running = True
        self._paused = False

        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=AUDIO_CHANNELS,
                dtype=AUDIO_DTYPE,
                blocksize=self._blocksize,
                callback=self._audio_callback,
            )
            self._stream.start()
            logger.info("WakeWordListener iniciado correctamente.")
        except Exception as e:
            self._running = False
            logger.warning("No se pudo iniciar InputStream de audio para wake word: %s", e)

    def stop(self) -> None:
        """Detiene el listener y libera recursos de audio."""
        self._running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.debug("Error cerrando stream de wake word: %s", e)
            finally:
                self._stream = None

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
            self._worker_thread = None
        logger.info("WakeWordListener detenido.")

    def pause(self) -> None:
        """Pausa la deteccion mientras Jota procesa o habla."""
        self._paused = True
        self._in_speech = False
        self._speech_frames.clear()
        self._silence_blocks = 0
        self._consecutive_speech_blocks = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def resume(self) -> None:
        """Reanuda la deteccion continua tras procesar respuesta."""
        self._pre_buffer.clear()
        self._speech_frames.clear()
        self._in_speech = False
        self._silence_blocks = 0
        self._consecutive_speech_blocks = 0
        self._paused = False

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """Procesa bloques continuos de audio con Voice Activity Detection."""
        if not self._running or self._paused:
            return

        raw = indata.astype(np.float32)
        rms = float(np.sqrt(np.mean(raw**2))) / 32768.0
        peak = float(np.max(np.abs(indata))) / 32768.0

        if self.level_callback and (self._in_speech or rms >= self.vad_threshold):
            try:
                self.level_callback(min(1.0, peak * 2.8))
            except Exception:
                pass

        if not self._in_speech:
            self._pre_buffer.append(indata.copy())
            if rms >= self.vad_threshold:
                self._consecutive_speech_blocks += 1
                if self._consecutive_speech_blocks >= 2:
                    self._in_speech = True
                    self._silence_blocks = 0
                    self._consecutive_speech_blocks = 0
                    self._speech_frames = list(self._pre_buffer)
                    self._speech_frames.append(indata.copy())
            else:
                self._consecutive_speech_blocks = 0
        else:
            self._speech_frames.append(indata.copy())
            if rms >= self.vad_threshold:
                self._silence_blocks = 0
            else:
                self._silence_blocks += 1

            if (
                self._silence_blocks >= self._silence_blocks_needed
                or len(self._speech_frames) >= self._max_speech_blocks
            ):
                frames_to_send = list(self._speech_frames)
                self._speech_frames.clear()
                self._in_speech = False
                self._silence_blocks = 0
                self._consecutive_speech_blocks = 0

                try:
                    self._queue.put_nowait(frames_to_send)
                except queue.Full:
                    pass

    def _worker_loop(self) -> None:
        """Hilo secundario que extrae fragmentos de la cola de voz."""
        AUDIO_TMP_DIR.mkdir(parents=True, exist_ok=True)
        while self._running:
            try:
                frames = self._queue.get(timeout=0.4)
            except queue.Empty:
                continue

            if self._paused or not frames:
                continue

            self._process_speech_frames(frames)

    def _process_speech_frames(self, frames: list[np.ndarray]) -> None:
        """Transcribe un fragmento detectado de voz y ejecuta el wake word si corresponde."""
        if not frames:
            return

        audio = np.concatenate(frames, axis=0)
        duration = len(audio) / self.sample_rate
        if duration < 0.4:
            return

        tmp_wav = AUDIO_TMP_DIR / f"wake_{uuid.uuid4().hex[:8]}.wav"
        try:
            _save_wav(audio, tmp_wav)
            text = stt.transcribe(tmp_wav)
            if not text:
                return

            has_wake, command = stt.extract_wake_word(text)
            if has_wake:
                logger.info(
                    "Wake word detectado en manos libres: frase=%r, comando=%r",
                    text,
                    command,
                )
                self.on_wake(command)
            else:
                logger.debug("Frase ambiental sin wake word: %r", text)
        except Exception as e:
            logger.error("Error en evaluacion de wake word: %s", e)
        finally:
            tmp_wav.unlink(missing_ok=True)

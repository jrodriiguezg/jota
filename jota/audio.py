"""Modulo de audio: grabacion desde microfono con limites y gestion segura de recursos."""

import logging
import re
import subprocess
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


class AudioDucker:
    """
    Gestiona la atenuacion automatica de volumen multimedia (audio ducking).
    Reduce el volumen de la musica activa o del sistema mientras el usuario habla con Jota
    para mejorar la captura de voz y transcripcion, y restaura el volumen al terminar.
    """

    def __init__(self, duck_volume_ratio: float = 0.15, duck_sink_ratio: float = 0.20):
        self.duck_volume_ratio = duck_volume_ratio
        self.duck_sink_ratio = duck_sink_ratio
        self.is_ducked = False
        self.duck_mode: str | None = None
        self.saved_playerctl_vol: float | None = None
        self.saved_sink_vol: float | None = None
        self._lock = threading.Lock()

    def duck(self) -> bool:
        """Atenua el volumen multimedia o del sistema. Devuelve True si se atenuo algo."""
        with self._lock:
            if self.is_ducked:
                return True
            try:
                # 1. Comprobar reproductores MPRIS activos (playerctl)
                res = subprocess.run(
                    ["playerctl", "status"],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                )
                if "Playing" in res.stdout:
                    v_res = subprocess.run(
                        ["playerctl", "volume"],
                        capture_output=True,
                        text=True,
                        timeout=1.0,
                    )
                    try:
                        vol = float(v_res.stdout.strip())
                    except ValueError:
                        vol = 1.0
                    self.saved_playerctl_vol = vol
                    subprocess.run(
                        ["playerctl", "volume", f"{self.duck_volume_ratio:.2f}"],
                        capture_output=True,
                        timeout=1.0,
                    )
                    self.is_ducked = True
                    self.duck_mode = "playerctl"
                    logger.info(
                        "Audio ducking activado via playerctl (volumen previo: %.2f)", vol
                    )
                    return True

                # 2. Si no hay reproductor MPRIS, atenuar sink por defecto de PipeWire
                wp_res = subprocess.run(
                    ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                )
                if wp_res.returncode == 0:
                    m = re.search(r"Volume:\s+([0-9.]+)", wp_res.stdout)
                    if m:
                        vol = float(m.group(1))
                        self.saved_sink_vol = vol
                        subprocess.run(
                            [
                                "wpctl",
                                "set-volume",
                                "@DEFAULT_AUDIO_SINK@",
                                f"{self.duck_sink_ratio:.2f}",
                            ],
                            capture_output=True,
                            timeout=1.0,
                        )
                        self.is_ducked = True
                        self.duck_mode = "wpctl"
                        logger.info(
                            "Audio ducking activado via wpctl (volumen previo: %.2f)", vol
                        )
                        return True
            except Exception as e:
                logger.debug("Error aplicando audio ducking: %s", e)
            return False

    def unduck(self, only_if_mode: str | None = None) -> bool:
        """Restaura el volumen previo. Si only_if_mode coincide o es None, restaura."""
        with self._lock:
            if not self.is_ducked:
                return False
            if only_if_mode and self.duck_mode != only_if_mode:
                return False
            try:
                if self.duck_mode == "playerctl" and self.saved_playerctl_vol is not None:
                    subprocess.run(
                        ["playerctl", "volume", f"{self.saved_playerctl_vol:.2f}"],
                        capture_output=True,
                        timeout=1.0,
                    )
                    logger.info(
                        "Audio ducking restaurado via playerctl (volumen: %.2f)",
                        self.saved_playerctl_vol,
                    )
                elif self.duck_mode == "wpctl" and self.saved_sink_vol is not None:
                    subprocess.run(
                        [
                            "wpctl",
                            "set-volume",
                            "@DEFAULT_AUDIO_SINK@",
                            f"{self.saved_sink_vol:.2f}",
                        ],
                        capture_output=True,
                        timeout=1.0,
                    )
                    logger.info(
                        "Audio ducking restaurado via wpctl (volumen: %.2f)", self.saved_sink_vol
                    )
            except Exception as e:
                logger.debug("Error restaurando audio ducking: %s", e)
            finally:
                self.is_ducked = False
                self.duck_mode = None
                self.saved_playerctl_vol = None
                self.saved_sink_vol = None
            return True

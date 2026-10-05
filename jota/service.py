"""
Servicio unificado de escucha de la tecla Copilot (Push-to-Talk) y procesamiento local.
Permite ejecutar el asistente en PC independientemente o embebido dentro del Bridge.
"""

import logging
import threading
import time
from pathlib import Path

from jota import audio, hotkey, llm, stt, tools, tts
from jota.config import (
    HANDSFREE_ENABLED,
    VAD_SILENCE_TIMEOUT,
    VAD_THRESHOLD,
)
from jota.ui.client import OrbClient
from jota.wakeword import WakeWordListener

logger = logging.getLogger(__name__)


class CopilotVoiceService:
    """
    Gestiona el ciclo de vida del asistente de voz (manos libres y push-to-talk):
    - Escucha de eventos de teclado en evdev (tecla Copilot)
    - Escucha continua opcional de wake word ('Jota') via WakeWordListener (manos libres)
    - Grabacion de audio reactiva
    - Transcripcion con Whisper
    - Fast intent routing (<1ms) y fallback a LLM local
    - Notificacion de estados al orbe visual sigiloso
    - Sintesis de voz TTS y reproduccion en altavoces
    """

    def __init__(self, orb: OrbClient | None = None, enable_handsfree: bool = HANDSFREE_ENABLED):
        self.orb = orb if orb is not None else OrbClient()
        self.recorder = audio.AudioRecorder(level_callback=lambda lvl: self.orb.set_level(lvl))
        self._processing_lock = threading.Lock()
        self._busy = False
        self._copilot: hotkey.CopilotHotkey | None = None

        self.wake_listener: WakeWordListener | None = None
        if enable_handsfree:
            try:
                self.wake_listener = WakeWordListener(
                    on_wake=self._on_wake_detected,
                    level_callback=lambda lvl: self.orb.set_level(lvl),
                    vad_threshold=VAD_THRESHOLD,
                    silence_timeout=VAD_SILENCE_TIMEOUT,
                )
            except Exception as e:
                logger.warning("No se pudo instanciar WakeWordListener: %s", e)

    def start(self) -> None:
        """Inicia el orbe, el listener de la tecla Copilot y la escucha manos libres."""
        self.orb.start()
        self._copilot = hotkey.CopilotHotkey(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._copilot.start()
        logger.info("CopilotVoiceService iniciado y escuchando teclas de teclado.")

        if self.wake_listener:
            try:
                self.wake_listener.start()
                logger.info("Escucha manos libres activa: di 'Jota' para activar.")
            except Exception as e:
                logger.warning("No se pudo iniciar escucha manos libres: %s", e)

    def stop(self) -> None:
        """Detiene la grabacion, hotkeys, listener manos libres y orbe."""
        if self._copilot:
            try:
                self._copilot.stop()
            except Exception as e:
                logger.debug("Error deteniendo hotkey: %s", e)
            self._copilot = None

        if self.wake_listener:
            try:
                self.wake_listener.stop()
            except Exception as e:
                logger.debug("Error deteniendo wake_listener: %s", e)
            self.wake_listener = None

        try:
            self.recorder.stop()
        except Exception:
            pass
        self.orb.set_state("idle")
        self.orb.quit()
        logger.info("CopilotVoiceService detenido.")

    def _on_key_press(self) -> None:
        """Se activa al pulsar la tecla Copilot."""
        if self._busy:
            logger.info("Jota esta ocupado, ignorando pulsacion.")
            return
        if self.wake_listener:
            self.wake_listener.pause()
        self.orb.set_state("listening", 0.0)
        self.recorder.start()

    def _on_key_release(self) -> None:
        """Se activa al soltar la tecla Copilot."""
        if not self.recorder.is_recording:
            return
        threading.Thread(target=self._process_audio, daemon=True).start()

    def _on_wake_detected(self, command: str) -> None:
        """Se activa cuando WakeWordListener detecta 'Jota' sin pulsar teclas."""
        if self._busy:
            logger.debug("Jota ocupado, ignorando wake word.")
            return
        threading.Thread(
            target=self._process_wake_command,
            args=(command,),
            daemon=True,
        ).start()

    def _process_wake_command(self, command: str) -> None:
        """Procesa una activacion manos libres tras pronunciar 'Jota'."""
        with self._processing_lock:
            self._busy = True
            if self.wake_listener:
                self.wake_listener.pause()
            try:
                if command.strip():
                    logger.info("Orden manos libres recibida con wake word: %r", command)
                    self.orb.set_state("thinking")
                    self._execute_command(command)
                    return

                logger.info("Wake word 'Jota' detectado sin orden. Esperando instruccion...")
                self.orb.set_state("listening", 0.0)
                follow_up = self._record_follow_up(timeout=5.0)
                if not follow_up:
                    logger.info("No se recibio orden posterior a 'Jota'.")
                    self.orb.set_state("idle")
                    return

                self.orb.set_state("thinking")
                text = stt.transcribe(follow_up)
                follow_up.unlink(missing_ok=True)
                if not text:
                    logger.info("Transcripcion vacia de orden posterior.")
                    self.orb.set_state("idle")
                    return

                clean = stt.strip_wake_word(text, require_wake_word=False)
                if not clean:
                    self.orb.set_state("idle")
                    return

                self._execute_command(clean)

            except Exception as e:
                logger.exception("Error procesando orden manos libres: %s", e)
                try:
                    self.orb.set_state("speaking")
                    tts.speak("Lo siento, ocurrio un error.")
                except Exception:
                    pass
                finally:
                    self.orb.set_state("idle")
            finally:
                self._busy = False
                if self.wake_listener:
                    self.wake_listener.resume()

    def _record_follow_up(self, timeout: float = 5.0) -> Path | None:
        """Graba audio tras escuchar solo la palabra 'Jota' hasta detectar silencio."""
        self.recorder.start()
        start = time.time()
        last_sound_time = start
        speech_started = False

        while time.time() - start < timeout:
            time.sleep(0.08)
            if self.recorder.last_peak > VAD_THRESHOLD:
                speech_started = True
                last_sound_time = time.time()
            elif speech_started and (time.time() - last_sound_time > VAD_SILENCE_TIMEOUT):
                break

        return self.recorder.stop()

    def _process_audio(self) -> None:
        with self._processing_lock:
            self._busy = True
            try:
                self._do_process()
            except Exception as e:
                logger.exception("Error procesando audio de Copilot: %s", e)
                try:
                    self.orb.set_state("speaking")
                    tts.speak("Lo siento, ocurrio un error.")
                except Exception:
                    pass
                finally:
                    self.orb.set_state("idle")
            finally:
                self._busy = False
                if self.wake_listener:
                    self.wake_listener.resume()

    def _do_process(self) -> None:
        audio_path = self.recorder.stop()
        if audio_path is None:
            logger.info("Sin audio capturado.")
            self.orb.set_state("idle")
            return

        try:
            self.orb.set_state("thinking")
            logger.info("Transcribiendo audio de Copilot...")
            text = stt.transcribe(audio_path)
            if not text:
                logger.info("Transcripcion vacia.")
                self.orb.set_state("idle")
                return

            logger.info("Escuche: %r", text)

            clean = stt.strip_wake_word(text, require_wake_word=False)
            if not clean:
                logger.info("Audio sin contenido tras limpieza de wake word.")
                self.orb.set_state("idle")
                return

            self._execute_command(clean)

        finally:
            audio_path.unlink(missing_ok=True)
            self.orb.set_state("idle")

    def _execute_command(self, clean: str) -> None:
        """Ejecuta una orden de voz via intencion rapida (<1ms) o via LLM."""
        fast_handled, fast_msg = tools.handle_intent(clean)
        if fast_handled:
            logger.info("Accion rapida resuelta sin LLM: %s", fast_msg)
            if fast_msg:
                self.orb.set_state("speaking")
                tts.speak(fast_msg)
            self.orb.set_state("idle")
            return

        logger.info("Enviando al LLM: %r", clean)
        self.orb.set_state("thinking")
        response = llm.ask(clean)
        if not response:
            logger.warning("LLM devolvio respuesta vacia.")
            self.orb.set_state("idle")
            return

        tool_handled, tool_msg = tools.handle_llm_output(response)
        if tool_handled:
            logger.info("Herramienta ejecutada via LLM: %s", tool_msg)
            spoken_text = llm.clean_text_for_tts(response) or tool_msg
            if spoken_text:
                self.orb.set_state("speaking")
                tts.speak(spoken_text)
            self.orb.set_state("idle")
            return

        clean_response = llm.clean_text_for_tts(response)
        if clean_response:
            logger.info("Respondiendo: %r", clean_response)
            self.orb.set_state("speaking")
            tts.speak(clean_response)
        self.orb.set_state("idle")

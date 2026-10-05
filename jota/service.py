"""
Servicio unificado de escucha de la tecla Copilot (Push-to-Talk) y procesamiento local.
Permite ejecutar el asistente en PC independientemente o embebido dentro del Bridge.
"""

import logging
import threading

from jota import audio, hotkey, llm, stt, tools, tts
from jota.ui.client import OrbClient

logger = logging.getLogger(__name__)


class CopilotVoiceService:
    """
    Gestiona el ciclo de vida del push-to-talk con la tecla Copilot:
    - Escucha de eventos de teclado en evdev
    - Grabacion de audio mientras se mantiene pulsada la tecla
    - Transcripcion con Whisper
    - Fast intent routing (<1ms) y fallback a LLM local
    - Notificacion de estados al orbe visual
    - Sintesis de voz TTS y reproduccion en altavoces
    """

    def __init__(self, orb: OrbClient | None = None):
        self.orb = orb if orb is not None else OrbClient()
        self.recorder = audio.AudioRecorder(level_callback=lambda lvl: self.orb.set_level(lvl))
        self._processing_lock = threading.Lock()
        self._busy = False
        self._copilot: hotkey.CopilotHotkey | None = None

    def start(self) -> None:
        """Inicia el orbe y el listener de la tecla Copilot."""
        self.orb.start()
        self._copilot = hotkey.CopilotHotkey(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._copilot.start()
        logger.info("CopilotVoiceService iniciado y escuchando teclas de teclado.")

    def stop(self) -> None:
        """Detiene la grabacion, el listener de teclado y el orbe."""
        if self._copilot:
            try:
                self._copilot.stop()
            except Exception as e:
                logger.debug("Error deteniendo hotkey: %s", e)
            self._copilot = None
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
        self.orb.set_state("listening", 0.0)
        self.recorder.start()

    def _on_key_release(self) -> None:
        """Se activa al soltar la tecla Copilot."""
        if not self.recorder.is_recording:
            return
        threading.Thread(target=self._process_audio, daemon=True).start()

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

            # Intent routing rapido (<1ms, 0% CPU para control multimedia, volumen, apps, etc.)
            fast_handled, fast_msg = tools.handle_intent(clean)
            if fast_handled:
                logger.info("Accion rapida resuelta sin LLM: %s", fast_msg)
                if fast_msg:
                    self.orb.set_state("speaking")
                    tts.speak(fast_msg)
                self.orb.set_state("idle")
                return

            logger.info("Enviando al LLM: %r", clean)
            response = llm.ask(clean)
            if not response:
                logger.warning("LLM devolvio respuesta vacia.")
                self.orb.set_state("idle")
                return

            # Comprobar llamada a herramienta generada por el LLM
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

        finally:
            audio_path.unlink(missing_ok=True)
            self.orb.set_state("idle")

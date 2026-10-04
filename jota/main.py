"""
main.py — Punto de entrada de Jota, Fase 1.

Flujo:
  1. Cargar modelo LLM
  2. Esperar tecla Copilot (pulsada)
  3. Grabar audio mientras este pulsada
  4. Transcribir con whisper.cpp
  5. Detectar y limpiar wake word "Jota"
  6. Enviar frase limpia al LLM
  7. Sintetizar respuesta con piper y reproducir por altavoces
  8. Volver al paso 2
"""

import logging
import signal
import sys
import threading

from jota import audio, hotkey, llm, stt, tools, tts
from jota.ui.client import OrbClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("jota")

# ── Estado global ─────────────────────────────────────────────────────────────

orb = OrbClient()
recorder = audio.AudioRecorder(level_callback=lambda lvl: orb.set_level(lvl))
_processing_lock = threading.Lock()
_busy = False  # evita procesar mientras ya se esta respondiendo


# ── Callbacks de la tecla ─────────────────────────────────────────────────────

def on_key_press() -> None:
    """Se llama cuando se pulsa la tecla Copilot."""
    global _busy
    if _busy:
        logger.info("Jota esta ocupado, ignorando pulsacion.")
        return
    orb.set_state("listening", 0.0)
    recorder.start()


def on_key_release() -> None:
    """Se llama cuando se suelta la tecla Copilot."""
    if not recorder.is_recording:
        return
    # Procesamos en hilo separado para no bloquear el listener de teclas
    threading.Thread(target=_process_audio, daemon=True).start()


# ── Procesamiento principal ───────────────────────────────────────────────────

def _process_audio() -> None:
    global _busy

    with _processing_lock:
        _busy = True
        try:
            _do_process()
        except Exception as e:
            logger.exception("Error procesando audio: %s", e)
            try:
                orb.set_state("speaking")
                tts.speak("Lo siento, ocurrio un error.")
            except Exception:
                pass
            finally:
                orb.set_state("idle")
        finally:
            _busy = False


def _do_process() -> None:
    # 1. Parar grabacion y obtener archivo WAV
    audio_path = recorder.stop()
    if audio_path is None:
        logger.info("Sin audio capturado.")
        orb.set_state("idle")
        return

    try:
        orb.set_state("thinking")
        # 2. Transcribir
        logger.info("Transcribiendo...")
        text = stt.transcribe(audio_path)
        if not text:
            logger.info("Transcripcion vacia.")
            orb.set_state("idle")
            return

        logger.info("Escuche: %r", text)

        # 3. Limpiar wake word
        clean = stt.strip_wake_word(text)
        if clean is None:
            logger.info("Sin wake word detectado, ignorando.")
            orb.set_state("idle")
            return

        # 3.5 Intent directo / rapido (<10ms para hora, volumen, multimedia, etc.)
        fast_handled, fast_msg = tools.handle_intent(clean)
        if fast_handled:
            logger.info("Intent rapido ejecutado: %s", fast_msg)
            if fast_msg:
                orb.set_state("speaking")
                tts.speak(fast_msg)
            orb.set_state("idle")
            return

        logger.info("Enviando directamente al LLM: %r", clean)

        # 4. Consultar directamente al LLM (Qwen deduce la intencion)
        response = llm.ask(clean)
        if not response:
            logger.warning("LLM devolvio respuesta vacia.")
            orb.set_state("idle")
            return

        # 5. Comprobar si el LLM emitio una llamada a herramienta
        tool_handled, tool_msg = tools.handle_llm_output(response)
        if tool_handled:
            logger.info("Herramienta ejecutada via LLM: %s", tool_msg)
            # Priorizar respuesta en lenguaje natural generada por el LLM si existe
            spoken_text = llm.clean_text_for_tts(response) or tool_msg
            if spoken_text:
                orb.set_state("speaking")
                tts.speak(spoken_text)
            orb.set_state("idle")
            return

        # 6. Sintetizar y reproducir respuesta conversacional del LLM
        clean_response = llm.clean_text_for_tts(response)
        if clean_response:
            logger.info("Respondiendo: %r", clean_response)
            orb.set_state("speaking")
            tts.speak(clean_response)
        else:
            logger.info("Respuesta vacia tras limpieza para TTS.")
        orb.set_state("idle")

    finally:
        # Limpieza de archivo de audio temporal por privacidad y espacio
        audio_path.unlink(missing_ok=True)
        orb.set_state("idle")


# ── Arranque ──────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("=" * 50)
    logger.info("  Jota -- Asistente de voz local  (Fase 2)")
    logger.info("=" * 50)

    # Iniciar orbe visual en segundo plano
    orb.start()

    # Cargar modelo LLM (puede tardar unos segundos)
    logger.info("Cargando modelo LLM, espera un momento...")
    llm.load_model()
    logger.info("Modelo listo.")

    # Iniciar listener de tecla Copilot
    copilot = hotkey.CopilotHotkey(
        on_press=on_key_press,
        on_release=on_key_release,
    )
    copilot.start()

    logger.info("Listo. Manten pulsada la tecla Copilot y habla.")
    logger.info("Ctrl+C para salir.")

    # Manejar Ctrl+C limpiamente
    def _shutdown(sig, frame):
        logger.info("Deteniendo Jota...")
        orb.set_state("idle")
        orb.quit()
        copilot.stop()
        recorder.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Bucle principal (el trabajo real esta en los hilos)
    signal.pause()


if __name__ == "__main__":
    main()

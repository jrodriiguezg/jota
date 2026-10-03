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

from jota import audio, hotkey, llm, stt, tts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("jota")

# ── Estado global ─────────────────────────────────────────────────────────────

recorder = audio.AudioRecorder()
_processing_lock = threading.Lock()
_busy = False  # evita procesar mientras ya se esta respondiendo


# ── Callbacks de la tecla ─────────────────────────────────────────────────────

def on_key_press() -> None:
    """Se llama cuando se pulsa la tecla Copilot."""
    global _busy
    if _busy:
        logger.info("Jota esta ocupado, ignorando pulsacion.")
        return
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
                tts.speak("Lo siento, ocurrio un error.")
            except Exception:
                pass
        finally:
            _busy = False


def _do_process() -> None:
    # 1. Parar grabacion y obtener archivo WAV
    audio_path = recorder.stop()
    if audio_path is None:
        logger.info("Sin audio capturado.")
        return

    try:
        # 2. Transcribir
        logger.info("Transcribiendo...")
        text = stt.transcribe(audio_path)
        if not text:
            logger.info("Transcripcion vacia.")
            return

        logger.info("Escuche: %r", text)

        # 3. Limpiar wake word
        clean = stt.strip_wake_word(text)
        if clean is None:
            logger.info("Sin wake word detectado, ignorando.")
            return

        logger.info("Pregunta para el LLM: %r", clean)

        # 4. Consultar LLM
        response = llm.ask(clean)
        if not response:
            logger.warning("LLM devolvio respuesta vacia.")
            return

        # 5. Sintetizar y reproducir
        logger.info("Respondiendo: %r", response)
        tts.speak(response)

    finally:
        # Limpieza de archivo de audio temporal por privacidad y espacio
        audio_path.unlink(missing_ok=True)


# ── Arranque ──────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("=" * 50)
    logger.info("  Jota -- Asistente de voz local  (Fase 1)")
    logger.info("=" * 50)

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
        copilot.stop()
        recorder.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Bucle principal (el trabajo real esta en los hilos)
    signal.pause()


if __name__ == "__main__":
    main()

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

from jota import llm
from jota.service import CopilotVoiceService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("jota")


def main() -> None:
    logger.info("=" * 50)
    logger.info("  Jota -- Asistente de voz local  (Fase 2)")
    logger.info("=" * 50)

    # Cargar modelo LLM (puede tardar unos segundos)
    logger.info("Cargando modelo LLM, espera un momento...")
    llm.load_model()
    logger.info("Modelo listo.")

    service = CopilotVoiceService()
    try:
        service.start()
    except Exception as e:
        logger.error("Error iniciando listener de tecla Copilot: %s", e)
        sys.exit(1)

    logger.info("Listo. Manten pulsada la tecla Copilot y habla.")
    logger.info("Ctrl+C para salir.")

    def _shutdown(sig, frame):
        logger.info("Deteniendo Jota...")
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    signal.pause()


if __name__ == "__main__":
    main()

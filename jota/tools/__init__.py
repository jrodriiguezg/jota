"""Sistema de herramientas y ejecucion de acciones de Jota (Fase 2)."""

import logging

from jota.tools.router import execute_tool, match_fast_intent, parse_llm_tool_call

logger = logging.getLogger(__name__)


def handle_intent(user_text: str) -> tuple[bool, str]:
    """
    Intenta resolver la peticion del usuario de forma inmediata mediante
    el enrutador rapido de intenciones (<10ms).
    Devuelve (manejado, mensaje_para_tts).
    """
    intent = match_fast_intent(user_text)
    if intent is None:
        return False, ""

    tool_name, args = intent
    logger.info("Intencion rapida detectada: %s (%s)", tool_name, args)
    success, message = execute_tool(tool_name, args)
    return True, message


def handle_llm_output(llm_response: str) -> tuple[bool, str]:
    """
    Si la respuesta generada por el LLM incluye una llamada a herramienta
    en formato TOOL: ..., la extrae y ejecuta.
    Devuelve (manejado, mensaje_para_tts).
    """
    parsed = parse_llm_tool_call(llm_response)
    if parsed is None:
        return False, ""

    tool_name, args = parsed
    logger.info("Llamada a herramienta detectada desde LLM: %s (%s)", tool_name, args)
    success, message = execute_tool(tool_name, args)
    return True, message

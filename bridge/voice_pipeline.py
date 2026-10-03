"""
Pipeline de procesamiento de voz y texto remoto para Jota Bridge.
Orquesta STT (whisper.cpp), LLM (Qwen3), ejecucion de herramientas y TTS (piper-tts).
"""

import logging
import uuid
from typing import Any

from bridge.config import BRIDGE_TEMP_DIR
from jota.llm import ask_llm, clean_text_for_tts
from jota.stt import strip_wake_word, transcribe
from jota.tools import execute_tool, parse_llm_tool
from jota.tts import synthesize_to_file

logger = logging.getLogger(__name__)


def process_remote_voice(
    audio_bytes: bytes,
    generate_audio: bool = True,
) -> dict[str, Any]:
    """
    Procesa un fragmento de audio recibido desde el cliente movil.
    Devuelve la transcripcion, respuesta del LLM, herramientas ejecutadas
    y ruta del audio sintetizado si corresponde.
    """
    if not audio_bytes:
        return {
            "success": False,
            "transcription": "",
            "response_text": "No se recibio ningun audio.",
            "tool_executed": None,
            "audio_id": None,
        }

    request_id = uuid.uuid4().hex[:8]
    input_wav = BRIDGE_TEMP_DIR / f"remote_in_{request_id}.wav"
    output_wav = BRIDGE_TEMP_DIR / f"remote_out_{request_id}.wav"

    try:
        input_wav.write_bytes(audio_bytes)

        # 1. STT: Whisper
        raw_text = transcribe(input_wav)
        if not raw_text:
            return {
                "success": True,
                "transcription": "",
                "response_text": "No he podido entender el audio.",
                "tool_executed": None,
                "audio_id": None,
            }

        # 2. Limpieza de wake word (en push-to-talk del movil no es obligatorio)
        prompt = strip_wake_word(raw_text, require_wake_word=False)
        if not prompt:
            return {
                "success": True,
                "transcription": raw_text,
                "response_text": "¿Si? ¿En que puedo ayudarte?",
                "tool_executed": None,
                "audio_id": None,
            }

        logger.info("Bridge - Peticion de voz recibida: %r", prompt)

        # 3. LLM: Inferencia
        llm_response = ask_llm(prompt)
        logger.info("Bridge - Respuesta LLM: %r", llm_response)

        # 4. Tool calling si el LLM emitio directiva TOOL:
        tool_result: dict[str, Any] | None = None
        tool_call = parse_llm_tool(llm_response)
        if tool_call:
            logger.info(
                "Bridge - Ejecutando herramienta remota: %s con %s",
                tool_call.name,
                tool_call.args,
            )
            result_str = execute_tool(tool_call.name, tool_call.args)
            tool_result = {
                "name": tool_call.name,
                "args": tool_call.args,
                "result": result_str,
            }

        # 5. Limpieza de texto para TTS y respuesta
        clean_text = clean_text_for_tts(llm_response)

        # 6. TTS remoto
        audio_id: str | None = None
        if generate_audio and clean_text:
            ok = synthesize_to_file(clean_text, output_wav)
            if ok and output_wav.exists():
                audio_id = output_wav.name

        return {
            "success": True,
            "transcription": raw_text,
            "prompt": prompt,
            "response_text": clean_text,
            "raw_response": llm_response,
            "tool_executed": tool_result,
            "audio_id": audio_id,
        }

    finally:
        input_wav.unlink(missing_ok=True)


def process_remote_text(
    prompt: str,
    generate_audio: bool = False,
) -> dict[str, Any]:
    """
    Procesa una peticion de texto directo sin pasar por STT.
    """
    if not prompt or not prompt.strip():
        return {
            "success": False,
            "prompt": "",
            "response_text": "Peticion vacia.",
            "tool_executed": None,
            "audio_id": None,
        }

    clean_prompt = prompt.strip()
    logger.info("Bridge - Peticion de texto recibida: %r", clean_prompt)

    # 1. LLM
    llm_response = ask_llm(clean_prompt)
    logger.info("Bridge - Respuesta LLM: %r", llm_response)

    # 2. Tool calling
    tool_result: dict[str, Any] | None = None
    tool_call = parse_llm_tool(llm_response)
    if tool_call:
        logger.info(
            "Bridge - Ejecutando herramienta remota: %s con %s",
            tool_call.name,
            tool_call.args,
        )
        result_str = execute_tool(tool_call.name, tool_call.args)
        tool_result = {
            "name": tool_call.name,
            "args": tool_call.args,
            "result": result_str,
        }

    clean_text = clean_text_for_tts(llm_response)

    # 3. TTS si se solicito
    audio_id: str | None = None
    if generate_audio and clean_text:
        request_id = uuid.uuid4().hex[:8]
        output_wav = BRIDGE_TEMP_DIR / f"remote_out_{request_id}.wav"
        ok = synthesize_to_file(clean_text, output_wav)
        if ok and output_wav.exists():
            audio_id = output_wav.name

    return {
        "success": True,
        "prompt": clean_prompt,
        "response_text": clean_text,
        "raw_response": llm_response,
        "tool_executed": tool_result,
        "audio_id": audio_id,
    }

"""LLM: interfaz con Qwen via llama-cpp-python con optimizacion de hilos y limpieza para TTS."""

import logging
import os
import re
from collections.abc import Generator

from llama_cpp import Llama

from jota.config import (
    LLM_ENABLE_THINKING,
    LLM_MODEL,
    LLM_N_CTX,
    LLM_N_GPU_LAYERS,
    LLM_PRESENCE_PENALTY,
    LLM_TEMPERATURE,
    LLM_TOP_K,
    LLM_TOP_P,
    SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

# Instancia global del modelo (se carga una vez al inicio)
_llm: Llama | None = None


def load_model() -> None:
    """Carga el modelo GGUF en memoria. Llamar al arrancar."""
    global _llm

    if not LLM_MODEL.exists():
        raise FileNotFoundError(
            f"Modelo GGUF no encontrado en {LLM_MODEL}.\n"
            "Ejecuta bash setup.sh para descargarlo automaticamente."
        )

    logger.info("Cargando modelo LLM: %s", LLM_MODEL.name)
    threads = min(8, os.cpu_count() or 4)

    _llm = Llama(
        model_path=str(LLM_MODEL),
        n_ctx=LLM_N_CTX,
        n_gpu_layers=LLM_N_GPU_LAYERS,
        n_threads=threads,
        verbose=False,
        chat_format="chatml",  # Qwen usa ChatML
    )
    logger.info("Modelo cargado con %d hilos de CPU.", threads)


def get_effective_system_prompt() -> str:
    """
    Devuelve el prompt del sistema configurado con la directiva de razonamiento
    adecuada (/no_think o /think) segun LLM_ENABLE_THINKING.
    """
    directive = "/think" if LLM_ENABLE_THINKING else "/no_think"
    if directive in SYSTEM_PROMPT:
        return SYSTEM_PROMPT
    return f"{SYSTEM_PROMPT}\n{directive}"


def ask(prompt: str) -> str:
    """
    Envia un prompt al LLM y devuelve la respuesta limpia lista para TTS.
    """
    if _llm is None:
        raise RuntimeError("Modelo no cargado. Llama a load_model() primero.")

    logger.debug("Enviando al LLM: %r", prompt)

    response = _llm.create_chat_completion(
        messages=[
            {"role": "system", "content": get_effective_system_prompt()},
            {"role": "user", "content": prompt},
        ],
        temperature=LLM_TEMPERATURE,
        top_p=LLM_TOP_P,
        top_k=LLM_TOP_K,
        presence_penalty=LLM_PRESENCE_PENALTY,
        max_tokens=256,  # respuestas cortas para TTS
        stream=False,
    )

    raw_text: str = response["choices"][0]["message"]["content"].strip()
    cleaned = clean_text_for_tts(raw_text)
    logger.info("Respuesta LLM: %r", cleaned)
    return cleaned


def clean_text_for_tts(text: str) -> str:
    """
    Limpia simbolos de markdown, bloques de razonamiento (<think>) y
    caracteres no hablados para que el motor TTS hable de forma natural.
    """
    # Eliminar bloques de razonamiento interno de Qwen3 (<think>...</think>)
    text = re.sub(r"<think>[\s\S]*?</think>", "", text)
    if "<think>" in text:
        text = re.sub(r"<think>[\s\S]*$", "", text)

    # Eliminar bloques de codigo
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Eliminar negritas, cursivas, tachados, codigo en linea y encabezados (*, _, ~, `, #)
    text = re.sub(r"[\*_~`#]", "", text)
    # Eliminar vinetas de listas (- item, + item)
    text = re.sub(r"^\s*[-+]\s+", "", text, flags=re.MULTILINE)
    # Limpiar multiples saltos de linea o espacios
    text = re.sub(r"\s+", " ", text).strip()
    return text


def ask_stream(prompt: str) -> Generator[str, None, None]:
    """
    Version streaming: yield de tokens para futuras integraciones.
    Por ahora no se usa en Fase 1, pero esta disponible para Fase 2.
    """
    if _llm is None:
        raise RuntimeError("Modelo no cargado.")

    for chunk in _llm.create_chat_completion(
        messages=[
            {"role": "system", "content": get_effective_system_prompt()},
            {"role": "user", "content": prompt},
        ],
        temperature=LLM_TEMPERATURE,
        top_p=LLM_TOP_P,
        top_k=LLM_TOP_K,
        presence_penalty=LLM_PRESENCE_PENALTY,
        max_tokens=256,
        stream=True,
    ):
        delta = chunk["choices"][0]["delta"]
        if "content" in delta:
            yield delta["content"]

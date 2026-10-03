"""LLM: interfaz con Qwen via llama-cpp-python."""

import logging
from typing import Generator

from llama_cpp import Llama

from jota.config import LLM_MODEL, LLM_N_CTX, LLM_N_GPU_LAYERS, LLM_TEMPERATURE, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Instancia global del modelo (se carga una vez al inicio)
_llm: Llama | None = None


def load_model() -> None:
    """Carga el modelo GGUF en memoria. Llamar al arrancar."""
    global _llm

    if not LLM_MODEL.exists():
        raise FileNotFoundError(
            f"Modelo GGUF no encontrado en {LLM_MODEL}.\n"
            "Descárgalo de HuggingFace y ajusta LLM_MODEL en config.py"
        )

    logger.info("Cargando modelo LLM: %s", LLM_MODEL.name)
    _llm = Llama(
        model_path=str(LLM_MODEL),
        n_ctx=LLM_N_CTX,
        n_gpu_layers=LLM_N_GPU_LAYERS,
        verbose=False,
        chat_format="chatml",  # Qwen usa ChatML
    )
    logger.info("Modelo cargado.")


def ask(prompt: str) -> str:
    """
    Envía un prompt al LLM y devuelve la respuesta completa como string.
    """
    if _llm is None:
        raise RuntimeError("Modelo no cargado. Llama a load_model() primero.")

    logger.debug("Enviando al LLM: %r", prompt)

    response = _llm.create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=LLM_TEMPERATURE,
        max_tokens=256,  # respuestas cortas para TTS
        stream=False,
    )

    text: str = response["choices"][0]["message"]["content"].strip()
    logger.info("Respuesta LLM: %r", text)
    return text


def ask_stream(prompt: str) -> Generator[str, None, None]:
    """
    Versión streaming: yield de tokens para futuras integraciones.
    Por ahora no se usa en Fase 1, pero está aquí para Fase 2.
    """
    if _llm is None:
        raise RuntimeError("Modelo no cargado.")

    for chunk in _llm.create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=LLM_TEMPERATURE,
        max_tokens=256,
        stream=True,
    ):
        delta = chunk["choices"][0]["delta"]
        if "content" in delta:
            yield delta["content"]

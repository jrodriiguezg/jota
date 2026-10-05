"""LLM: interfaz nativa con Qwen via llama-cpp-python con optimizacion y guardarailes."""

import logging
import os
import re
import time
from collections.abc import Generator

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None

from jota.config import (
    LLM_ENABLE_THINKING,
    LLM_MODEL,
    LLM_N_CTX,
    LLM_N_GPU_LAYERS,
    LLM_PRESENCE_PENALTY,
    LLM_TEMPERATURE,
    LLM_THREADS,
    LLM_TOP_K,
    LLM_TOP_P,
    SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

# Instancia global del modelo llama-cpp
_llm = None



class ConversationMemory:
    """
    Gestiona el historial de turnos recientes para permitir seguimiento de contexto
    con caducidad automatica (TTL) y limite estricto de turnos.
    """

    def __init__(self, max_turns: int = 4, ttl_seconds: float = 180.0):
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self.turns: list[dict[str, str]] = []
        self.last_activity: float = 0.0

    def add_user_message(self, content: str) -> None:
        self._check_ttl()
        self.turns.append({"role": "user", "content": content})
        self._trim()
        self.last_activity = time.time()

    def add_assistant_message(self, content: str) -> None:
        self._check_ttl()
        self.turns.append({"role": "assistant", "content": content})
        self._trim()
        self.last_activity = time.time()

    def get_history(self) -> list[dict[str, str]]:
        self._check_ttl()
        return list(self.turns)

    def clear(self) -> None:
        self.turns.clear()
        self.last_activity = 0.0

    def _check_ttl(self) -> None:
        if self.last_activity and (time.time() - self.last_activity) > self.ttl_seconds:
            self.clear()

    def _trim(self) -> None:
        max_messages = self.max_turns * 2
        if len(self.turns) > max_messages:
            self.turns = self.turns[-max_messages:]


# Instancia compartida global de memoria conversacional
conversation_memory = ConversationMemory()


# ── Guardarrailes de Seguridad contra Inyeccion de Prompts ────────────────────

INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+|previous\s+|your\s+|prior\s+|any\s+)*instructions",
    r"ignora\s+(?:todas\s+|las\s+|tus\s+|cualquier\s+|previas\s+)*instrucciones",
    r"haz\s+caso\s+omiso\s+(?:a\s+tus\s+reglas|de\s+las\s+instrucciones|a\s+las\s+instrucciones|a\s+lo\s+anterior)",
    r"you\s+are\s+now\s+in\s+developer\s+mode",
    r"ahora\s+estas\s+en\s+modo\s+desarrollador",
    r"system\s+override",
    r"reveal\s+(?:your\s+)?system\s+prompt",
    r"muestra\s+(?:tu\s+)?prompt\s+de\s+sistema",
    r"dime\s+(?:tus\s+)?instrucciones\s+internas",
]

CONTEXT_RESET_PATTERNS = [
    r"^(olvida\s+(la\s+)?conversacion|olvida\s+lo\s+anterior)$",
    r"^(reinicia\s+(el\s+)?contexto|nueva\s+conversacion|borra\s+(el\s+)?historial)$",
]


def check_prompt_safety(prompt: str) -> tuple[bool, str | None]:
    """
    Verifica si el prompt contiene intentos de inyeccion o subversion del asistente.
    Devuelve (es_seguro, mensaje_rechazo_o_none).
    """
    p_lower = prompt.lower().strip()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, p_lower):
            logger.warning("Guardrail: Intento de inyeccion detectado en el prompt: %r", prompt)
            return False, "Por motivos de seguridad, no puedo modificar mis directivas operativas."
    return True, None


def load_model() -> None:
    """Carga el modelo GGUF en memoria con limite estricto de hilos. Llamar al arrancar."""
    global _llm
    if _llm is not None:
        return

    if Llama is None:
        logger.warning(
            "llama-cpp-python no esta instalado. El modo LLM local no estara disponible."
        )
        return

    if not LLM_MODEL.exists():
        raise FileNotFoundError(
            f"Modelo GGUF no encontrado en {LLM_MODEL}.\n"
            "Ejecuta bash setup.sh para descargarlo automaticamente."
        )

    logger.info("Cargando modelo LLM local: %s", LLM_MODEL.name)
    threads = max(1, min(LLM_THREADS, os.cpu_count() or 4))

    _llm = Llama(
        model_path=str(LLM_MODEL),
        n_ctx=LLM_N_CTX,
        n_gpu_layers=LLM_N_GPU_LAYERS,
        n_threads=threads,
        verbose=False,
        chat_format="chatml",
    )
    logger.info("Modelo local cargado con %d hilos de CPU (consumo acotado).", threads)


def get_effective_system_prompt() -> str:
    """
    Devuelve el prompt del sistema configurado con contexto temporal actual
    y la directiva de razonamiento adecuada (/no_think o /think) segun LLM_ENABLE_THINKING.
    """
    from datetime import datetime

    now = datetime.now()
    dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    dia_semana = dias[now.weekday()]
    mes = meses[now.month - 1]
    time_info = (
        f"Contexto temporal del sistema: Hoy es {dia_semana}, {now.day} de {mes} de {now.year}. "
        f"Hora local actual: {now.strftime('%H:%M')}."
    )
    directive = "/think" if LLM_ENABLE_THINKING else "/no_think"
    prompt = f"{SYSTEM_PROMPT}\n\n{time_info}"
    if directive in prompt:
        return prompt
    return f"{prompt}\n{directive}"


def ask(prompt: str, use_history: bool = True) -> str:
    """
    Envia un prompt al LLM nativo y devuelve la respuesta limpia lista para TTS.
    Gestiona memoria contextual multi-turno y comprobaciones de seguridad.
    """
    clean_p = prompt.strip()

    # 1. Comprobar reinicio manual de conversacion
    for r_pat in CONTEXT_RESET_PATTERNS:
        if re.search(r_pat, clean_p.lower()):
            conversation_memory.clear()
            return "Contexto conversacional reiniciado. ¿En que puedo ayudarte?"

    # 2. Guardrail de seguridad
    is_safe, safety_msg = check_prompt_safety(clean_p)
    if not is_safe and safety_msg:
        return safety_msg

    if _llm is None:
        load_model()
    if _llm is None:
        raise RuntimeError("Modelo no cargado. Llama a load_model() primero.")

    logger.debug("Enviando al LLM: %r", clean_p)

    # 3. Construccion de mensajes con memoria
    messages: list[dict[str, str]] = [
        {"role": "system", "content": get_effective_system_prompt()}
    ]
    if use_history:
        messages.extend(conversation_memory.get_history())
    messages.append({"role": "user", "content": clean_p})

    response = _llm.create_chat_completion(
        messages=messages,
        temperature=LLM_TEMPERATURE,
        top_p=LLM_TOP_P,
        top_k=LLM_TOP_K,
        presence_penalty=LLM_PRESENCE_PENALTY,
        max_tokens=256,
        stream=False,
    )

    raw_text: str = response["choices"][0]["message"]["content"].strip()

    # Eliminar bloques <think> de Qwen3 preservando directivas de herramientas
    raw_text = re.sub(r"<think>[\s\S]*?</think>", "", raw_text)
    if "<think>" in raw_text:
        raw_text = re.sub(r"<think>[\s\S]*$", "", raw_text)
    raw_text = raw_text.strip()

    # 4. Actualizar memoria si no fue un comando directo de herramienta
    if use_history and not raw_text.startswith("TOOL:"):
        conversation_memory.add_user_message(clean_p)
        conversation_memory.add_assistant_message(raw_text)

    logger.info("Respuesta LLM: %r", raw_text)
    return raw_text




def clean_text_for_tts(text: str) -> str:
    """
    Limpia simbolos de markdown, tablas, URLs, emojis, bloques de razonamiento (<think>),
    directivas TOOL: y caracteres no hablados para que el motor TTS hable de forma natural.
    """
    # Eliminar bloques de razonamiento interno de Qwen3 (<think>...</think>)
    text = re.sub(r"<think>[\s\S]*?</think>", "", text)
    if "<think>" in text:
        text = re.sub(r"<think>[\s\S]*$", "", text)

    # Eliminar directivas TOOL: para que el motor TTS nunca las lea en voz alta
    text = re.sub(r"TOOL:\s*.*$", "", text, flags=re.MULTILINE)

    # Eliminar bloques de codigo
    text = re.sub(r"```[\s\S]*?```", "", text)

    # Limpiar tablas markdown: eliminar lineas divisorias (|---|---|) y reemplazar | por espacios
    text = re.sub(r"(?m)^\s*\|?[\s\-:|]+\|\s*$", "", text)
    text = text.replace("|", " ")

    # Simplificar URLs para evitar que el sintetizador lea http://...
    text = re.sub(r"https?://(?:www\.)?([a-zA-Z0-9.-]+)(?:/[^\s]*)?", r"enlace de \1", text)

    # Eliminar negritas, cursivas, tachados, codigo en linea y encabezados (*, _, ~, `, #)
    text = re.sub(r"[\*_~`#]", "", text)

    # Eliminar vinetas de listas (- item, + item)
    text = re.sub(r"^\s*[-+]\s+", "", text, flags=re.MULTILINE)

    # Eliminar emojis comunes para que piper no pronuncie descripciones extranas
    emoji_pattern = re.compile(
        r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50-\u2b55]",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub("", text)

    # Limpiar multiples saltos de linea o espacios
    text = re.sub(r"\s+", " ", text).strip()
    return text


def ask_stream(prompt: str) -> Generator[str, None, None]:
    """
    Version streaming: yield de tokens para futuras integraciones.
    """
    if _llm is None:
        load_model()
    if _llm is None:
        raise RuntimeError("Modelo no cargado.")

    messages = [
        {"role": "system", "content": get_effective_system_prompt()},
        *conversation_memory.get_history(),
        {"role": "user", "content": prompt},
    ]


    for chunk in _llm.create_chat_completion(
        messages=messages,
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


# Alias conveniente
ask_llm = ask


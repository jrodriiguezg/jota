"""
Herramienta de comprension visual de pantalla usando VLM local (Moondream2 / Qwen2-VL / Ollama).
"""

import base64
import json
import logging
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Tuple

from jota.llm import clean_text_for_tts

logger = logging.getLogger(__name__)

DEFAULT_VISION_URL = os.getenv("JOTA_VISION_URL", "http://localhost:11434/api/generate")
DEFAULT_VISION_MODEL = os.getenv("JOTA_VISION_MODEL", "moondream")


def capture_screen_png_bytes() -> bytes | None:
    """Captura la pantalla actual en Wayland usando grim y retorna los bytes PNG."""
    grim_bin = shutil.which("grim")
    if not grim_bin:
        logger.warning("grim no encontrado en el sistema.")
        return None

    try:
        proc = subprocess.run(
            [grim_bin, "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
    except Exception as e:
        logger.error("Error al capturar pantalla con grim: %s", e)
    return None


def query_vision_model(
    image_bytes: bytes,
    question: str,
    endpoint: str = DEFAULT_VISION_URL,
    model: str = DEFAULT_VISION_MODEL,
    timeout: int = 15,
) -> Tuple[bool, str]:
    """
    Envia la imagen codificada en Base64 junto con la pregunta al modelo de vision (Ollama).
    Retorna (exito, texto_limpio).
    """
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    clean_question = question.strip() if question else "Que hay en la pantalla?"

    system_instruction = (
        "Eres el asistente visual de Jota para Linux. "
        "Analiza la captura de pantalla y responde de forma breve, "
        "concisa, directa y sin ningun emoji a la pregunta del usuario."
    )

    payload = {
        "model": model,
        "prompt": f"{system_instruction}\nPregunta: {clean_question}",
        "images": [b64_image],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 120,
        },
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                result = json.loads(response.read().decode("utf-8"))
                raw_response = result.get("response", "").strip()
                cleaned = clean_text_for_tts(raw_response)
                return True, cleaned if cleaned else "No se obtuvo respuesta del modelo de vision."
    except urllib.error.URLError as e:
        logger.warning("No se pudo conectar al endpoint de vision local (%s): %s", endpoint, e)
        return False, "El servicio local de vision no esta disponible en este momento."
    except Exception as e:
        logger.error("Error consultando el modelo de vision: %s", e)
        return False, "Error al procesar la captura con el modelo de vision."

    return False, "No se pudo obtener respuesta del modelo de vision."


def analyze_screen(question: str = "Que hay en pantalla?") -> Tuple[bool, str]:
    """
    Toma una captura de pantalla y la analiza con el modelo de vision local.
    Devuelve (exito, mensaje_para_tts).
    """
    logger.info("Iniciando analisis visual de pantalla: %s", question)
    img_bytes = capture_screen_png_bytes()

    if not img_bytes:
        # Fallback a captura de pc_ops si esta disponible
        try:
            from bridge.pc_ops import capture_screen_bytes
            img_bytes = capture_screen_bytes()
        except Exception:
            pass

    if not img_bytes:
        return False, "No se pudo capturar la pantalla para el analisis visual."

    ok, reply = query_vision_model(img_bytes, question)
    return ok, reply

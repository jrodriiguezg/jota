"""Enrutador de intenciones: reconocimiento rapido (<10ms) y parseo de llamadas del LLM."""

import logging
import re

from jota.tools.apps import launch_application
from jota.tools.media import playback_control, set_volume, toggle_mute
from jota.tools.screenshot import take_screenshot_to_clipboard
from jota.tools.search import open_web_search

logger = logging.getLogger(__name__)


def match_fast_intent(text: str) -> tuple[str, dict] | None:
    """
    Evalua el texto del usuario con reglas de intencion inmediata.
    Si coincide, devuelve (tool_name, kwargs) para ejecucion instantanea sin esperar al LLM.
    """
    clean = text.lower().strip()
    # Quitar signos de puntuacion iniciales/finales
    clean = re.sub(r"^[¿¡\s]+|[?!.,\s]+$", "", clean)

    # 1. Captura de pantalla
    if re.search(
        r"^(haz\s+una\s+|toma\s+una\s+)?captura(\s+de\s+pantalla|\s+la\s+pantalla|\s+pantalla)?$"
        r"|^captura(r)?(\s+la)?\s+pantalla"
        r"|^copia(r)?\s+(la\s+)?pantalla(\s+en\s+el\s+portapapeles)?"
        r"|^screenshot$",
        clean,
    ):
        return "screenshot", {}

    # 2. Control de volumen
    if re.search(
        r"^(sube|subir|aumenta|aumentar|mas|subeme)\s+(el\s+)?(volumen|sonido|audio)",
        clean,
    ):
        return "volume_control", {"direction": "up"}

    if re.search(
        r"^(baja|bajar|disminuye|disminuir|menos|bajame)\s+(el\s+)?(volumen|sonido|audio)",
        clean,
    ):
        return "volume_control", {"direction": "down"}

    if re.search(
        r"^(silencia|silenciar|mute|quitar\s+silencio|desilenciar)"
        r"(\s+(el\s+)?(audio|sonido|volumen))?$",
        clean,
    ):
        return "volume_control", {"action": "mute"}

    # 3. Control de reproduccion
    if re.search(
        r"^(pausa|pausar|para|parar|deten|detener)"
        r"(\s+(la\s+)?(musica|cancion|reproduccion|audio))?$",
        clean,
    ):
        return "media_control", {"action": "pause"}

    if re.search(
        r"^(reproduce|reproducir|reanuda|reanudar|continua|continuar|dale\s+al\s+play|play)"
        r"(\s+(la\s+)?(musica|cancion|reproduccion))?$",
        clean,
    ):
        return "media_control", {"action": "play"}

    if re.search(
        r"^(siguiente|cambia(\s+de)?|pasa(\s+de)?|otra|pon\s+la\s+siguiente)"
        r"\s+(cancion|pista|musica|tema)?$|^siguiente$",
        clean,
    ):
        return "media_control", {"action": "next"}

    if re.search(
        r"^(cancion|pista|tema)?\s*anterior$|^vuelve\s+a\s+la\s+cancion\s+anterior$",
        clean,
    ):
        return "media_control", {"action": "previous"}

    # 4. Busqueda web
    search_prefix = re.search(
        r"^(por\s+favor\s+)?(busca|buscame|buscar|encuentra)\s+en\s+(la\s+)?(web|google|internet)\s+(.+)$",
        clean,
    )
    if search_prefix:
        query = search_prefix.group(5).strip()
        return "web_search", {"query": query}

    search_suffix = re.search(
        r"^(por\s+favor\s+)?(busca|buscame|buscar|encuentra)\s+(.+)\s+en\s+(la\s+)?(web|google|internet)$",
        clean,
    )
    if search_suffix:
        query = search_suffix.group(3).strip()
        return "web_search", {"query": query}

    # 5. Abrir aplicaciones
    open_app_match = re.search(
        r"^(por\s+favor\s+|puedes\s+)?(abre|abrir|lanza|lanzar|ejecuta|ejecutar)\s+(el\s+|la\s+|los\s+|las\s+|un\s+|una\s+)?(.+)$",
        clean,
    )
    if open_app_match:
        app_target = open_app_match.group(4).strip()
        return "open_app", {"name": app_target}

    return None


def parse_llm_tool_call(llm_output: str) -> tuple[str, dict] | None:
    """
    Analiza la respuesta del LLM buscando directivas TOOL: nombre(argumentos).
    """
    match = re.search(r"TOOL:\s*([a-zA-Z0-9_]+)\((.*?)\)", llm_output)
    if not match:
        return None

    tool_name = match.group(1).strip()
    args_str = match.group(2).strip()
    args: dict = {}

    # Extraer argumentos clave-valor simples (ej: action='up', name='dolphin', query='...')
    arg_matches = re.findall(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*['\"](.*?)['\"]", args_str)
    for k, v in arg_matches:
        args[k] = v

    if tool_name in ("volume_control", "set_volume"):
        action = args.get("action", "")
        direction = args.get("direction", "")
        if action == "mute":
            return "volume_control", {"action": "mute"}
        if action in ("up", "down"):
            return "volume_control", {"direction": action}
        if direction in ("up", "down"):
            return "volume_control", {"direction": direction}
        return "volume_control", {"direction": "up"}

    if tool_name in ("media_control", "playback_control"):
        action = args.get("action", "play_pause")
        return "media_control", {"action": action}

    if tool_name in ("screenshot", "take_screenshot"):
        return "screenshot", {}

    if tool_name in ("open_app", "launch_app"):
        name = args.get("name") or args.get("app_name") or args.get("target", "")
        return "open_app", {"name": name}

    if tool_name in ("web_search", "search_web"):
        query = args.get("query", "")
        return "web_search", {"query": query}

    return None


def execute_tool(tool_name: str, args: dict) -> tuple[bool, str]:
    """
    Despacha la ejecucion de la herramienta segun su nombre y argumentos.
    Devuelve (exito, mensaje_para_tts).
    """
    logger.info("Ejecutando herramienta: %s con argumentos %s", tool_name, args)

    if tool_name == "screenshot":
        return take_screenshot_to_clipboard()

    if tool_name == "volume_control":
        if args.get("action") == "mute":
            return toggle_mute()
        direction = args.get("direction", "up")
        return set_volume(direction)

    if tool_name == "media_control":
        action = args.get("action", "play_pause")
        return playback_control(action)

    if tool_name == "open_app":
        name = args.get("name", "")
        return launch_application(name)

    if tool_name == "web_search":
        query = args.get("query", "")
        return open_web_search(query)

    return False, f"Herramienta no implementada: {tool_name}"

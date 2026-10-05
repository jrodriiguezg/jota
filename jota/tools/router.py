"""Enrutador de intenciones: reconocimiento rapido (<10ms) y parseo de llamadas del LLM."""

import logging
import re
from typing import NamedTuple

from jota.tools.apps import launch_application
from jota.tools.media import playback_control, set_volume, toggle_mute
from jota.tools.screenshot import take_screenshot_to_clipboard
from jota.tools.search import open_web_search

logger = logging.getLogger(__name__)


def normalize_speech_command(text: str) -> str:
    """
    Normaliza el texto corrigiendo confusiones foneticas comunes de Whisper en espanol.
    Ejemplos:
      - 'habla terminal' -> 'abre terminal'
      - 'a ver a terminar' -> 'abre terminal'
      - 'abre feisfin' -> 'abre feishin'
      - 'abre dolfin' -> 'abre dolphin'
    """
    clean = text.lower().strip()
    clean = re.sub(r"^[¿¡\s]+|[?!.,\s]+$", "", clean)

    # Confusiones de verbos de apertura
    clean = re.sub(r"^(por favor\s+|puedes\s+)?(habla|hablar|habre)\s+", r"\1abre ", clean)
    clean = re.sub(r"^(por favor\s+|puedes\s+)?(a\s+ver\s+(a\s+)?|haber\s+)", r"\1abre ", clean)

    # Confusiones de nombres comunes de apps
    clean = re.sub(r"\b(terminar|terminado)\b", "terminal", clean)
    clean = re.sub(r"\bfeisfin\b", "feishin", clean)
    clean = re.sub(r"\bdolfin\b", "dolphin", clean)

    return clean


def match_fast_intent(text: str) -> tuple[str, dict] | None:
    """
    Evalua el texto del usuario con reglas de intencion inmediata.
    Si coincide, devuelve (tool_name, kwargs) para ejecucion instantanea sin esperar al LLM.
    """
    clean = normalize_speech_command(text)

    # 1. Captura de pantalla
    if re.search(
        r"^(haz\s+una\s+|toma\s+una\s+)?captura(\s+de\s+pantalla|\s+la\s+pantalla|\s+pantalla)?$"
        r"|^captura(r)?(\s+la)?\s+pantalla"
        r"|^copia(r)?\s+(la\s+)?pantalla(\s+en\s+el\s+portapapeles)?"
        r"|^screenshot$",
        clean,
    ):
        return "screenshot", {}

    # 1b. Vision y analisis de pantalla con VLM
    if re.search(
        r"^(que\s+error\s+(me\s+)?(esta\s+dando|da|sale\s+en)\s+(la\s+)?(terminal|consola|pantalla))"
        r"|^(explica(me)?(\s+que\s+hay\s+en|\s+la)?|que\s+hay\s+en|que\s+tengo\s+en|mira|analiza)\s+(la\s+)?pantalla"
        r"|^resume(\s+lo\s+que\s+estoy\s+leyendo|\s+la\s+pantalla)",
        clean,
    ):
        return "analyze_screen", {"question": text}

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
        r"^(pausa|pausar|para|parar|deten|detener|corta|cortar)"
        r"(\s+(la\s+|el\s+)?(m[uú]sica|canci[oó]n|reproducci[oó]n|audio|pista|tema))?$",
        clean,
    ):
        return "media_control", {"action": "pause"}

    if re.search(
        r"^(reproduce|reproducir|reanuda|reanudar|continua|continuar|dale\s+al\s+play|play)"
        r"(\s+(la\s+|el\s+)?(reproducci[oó]n(\s+de(\s+la)?\s+(m[uú]sica|canci[oó]n|audio))?|m[uú]sica|canci[oó]n|tema|pista|audio))?$"
        r"|^(inicia|iniciar|comienza|comenzar|empieza|empezar|pon|arranca|arrancar)"
        r"\s+(la\s+|el\s+)?(reproducci[oó]n(\s+de(\s+la)?\s+(m[uú]sica|canci[oó]n|audio))?|m[uú]sica|canci[oó]n|tema|pista|audio)$"
        r"|^inicia(\s+la)?\s+reproducci[oó]n"
        r"|^dale\s+al\s+play$"
        r"|^play$",
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
        r"^(por\s+favor\s+|puedes\s+)?"
        r"(abre|abrir|lanza|lanzar|ejecuta|ejecutar|inicia|iniciar|pon|arranca|arrancar)\s+"
        r"(el\s+|la\s+|los\s+|las\s+|un\s+|una\s+)?(.+)$",
        clean,
    )
    if open_app_match:
        app_target = open_app_match.group(4).strip()
        return "open_app", {"name": app_target}

    # 5b. Nombre directo de aplicacion o alias conocido (ej: 'reproductor de musica', 'feishin', 'terminal')
    clean_app_cand = re.sub(r"^(el|la|los|las|un|una)\s+", "", clean).strip()
    from jota.config import APP_ALIASES, CUSTOM_APP_MAPPINGS
    if clean_app_cand in APP_ALIASES or clean_app_cand in CUSTOM_APP_MAPPINGS:
        return "open_app", {"name": clean_app_cand}


    # 6. Hora y fecha del sistema
    if re.search(
        r"^(que\s+hora\s+es|dime\s+la\s+hora|hora(\s+actual)?|que\s+hora\s+tienes)$",
        clean,
    ):
        return "get_current_time", {"mode": "time"}

    if re.search(
        r"^(que\s+dia\s+es(\s+hoy)?|que\s+fecha\s+es(\s+hoy)?|en\s+que\s+dia\s+estamos|cual\s+es\s+la\s+fecha)$",
        clean,
    ):
        return "get_current_time", {"mode": "date"}

    # 7. Ver o capturar pantalla del PC
    if re.search(
        r"^(muestrame|muestra|ver|ensenad?|captura|pon)\s+(la\s+)?pantalla(\s+del\s+pc)?$|^pantalla\s+del\s+pc$",
        clean,
    ):
        return "screenshot", {}

    # 8. Espacios de trabajo (Workspaces)
    ws_switch = re.search(
        r"^(pasa|pasad|pasar|cambia|cambiad|cambiar|ve|id|ir|saltar)\s+al\s+escritorio\s+(\d+)$"
        r"|^(pasa|pasad|pasar|cambia|cambiad|ve|id)\s+a\s+workspace\s+(\d+)$"
        r"|^(escritorio|workspace)\s+(\d+)$",
        clean,
    )
    if ws_switch:
        val = ws_switch.group(2) or ws_switch.group(4) or ws_switch.group(6)
        return "switch_workspace", {"target": int(val)}

    ws_move = re.search(
        r"^(mueve|mueved|mover|mueva)\s+"
        r"(?:(la\s+)?(ventana|aplicaci[oó]n|app)\s+(de\s+)?)?"
        r"(?:(el|la|los|las)\s+)?"
        r"(.+?)?\s*"
        r"al\s+(?:escritorio|workspace)\s+(\d+)$",
        clean,
    )
    if ws_move:
        raw_app = (ws_move.group(6) or "").strip()
        if raw_app in ("ventana", "aplicacion", "aplicación", "app", "la ventana", "la app", "el", "la"):
            raw_app = ""
        val = ws_move.group(7)
        res_dict = {"target": int(val)}
        if raw_app:
            res_dict["app"] = raw_app
        return "move_to_workspace", res_dict



    # 9. Clima y tiempo
    weather_match = re.search(
        r"^(que\s+tiempo\s+hace|va\s+a\s+llover|temperatura|el\s+clima|el\s+tiempo)\s+(hoy\s+)?(en|de|para|una)?\s*([a-zA-ZáéíóúÁÉÍÓÚñÑ\s]+)$",
        clean,
    )
    if weather_match:
        city_raw = weather_match.group(4).strip()
        cleaned_city = re.sub(
            r"^(en|de|para|una|el|la)\s+", "", city_raw, flags=re.IGNORECASE
        ).strip()
        if cleaned_city:
            return "get_weather", {"city": cleaned_city.capitalize()}

    # 10. Confirmacion y cancelacion de acciones de energia
    if re.search(r"^(si\s*,?\s*confirma(r)?|confirmo|confirma|procede)$", clean):
        return "system_power", {"action": "confirm"}
    if re.search(r"^(cancela(r)?|no\s*,?\s*cancela(r)?|no\s+lo\s+hagas|abortar)$", clean):
        return "system_power", {"action": "cancel"}

    # 11. Bateria del PC
    if re.search(
        r"^(cuanta\s+bateria\s+le\s+queda(\s+al\s+(pc|portatil|ordenador))?|(nivel\s+de\s+|estado\s+de\s+)?bateria(\s+del\s+(pc|portatil|ordenador))?)$",
        clean,
    ):
        return "get_pc_battery", {}

    # 12. Cancion que esta sonando actualmente
    if re.search(
        r"^(que\s+(cancion|tema|pista)\s+(esta\s+sonando|suena)|que\s+cancion\s+es(\s+esta)?|que\s+suena|que\s+esta\s+sonando)$",
        clean,
    ):
        return "get_now_playing", {}

    # 13. Cancelacion de temporizadores
    if re.search(
        r"^(cancela|cancelar|para|parar|deten|detener)\s+(el\s+|la\s+)?(temporizador|alarma|aviso)$",
        clean,
    ):
        return "cancel_timer", {}

    # 14. Busqueda en notas
    notes_search = re.search(r"^(busca|buscame|buscar)\s+en\s+(mis\s+)?notas\s+(.+)$", clean)
    if notes_search:
        return "manage_notes", {"action": "search", "query": notes_search.group(3).strip()}

    return None


class ToolCall(NamedTuple):
    name: str
    args: dict


def parse_llm_tool_call(llm_output: str) -> ToolCall | None:
    """
    Analiza la respuesta del LLM buscando directivas TOOL: nombre(argumentos) o TOOL: nombre.
    Tolera nombres de herramientas con y sin guion bajo, nombres directos de aplicacion, etc.
    Retorna un ToolCall (NamedTuple) compatible con desempaquetado de tupla y atributos
    .name, .args.
    """
    raw = _parse_llm_tool_call_raw(llm_output)
    if raw is None:
        return None
    return ToolCall(raw[0], raw[1])


def _parse_llm_tool_call_raw(llm_output: str) -> tuple[str, dict] | None:
    match = re.search(r"TOOL:\s*([a-zA-Z0-9_]+)(?:\((.*?)\))?", llm_output)
    if not match:
        return None

    raw_tool_name = match.group(1).strip()
    norm_name = raw_tool_name.lower().replace("_", "")
    args_str = match.group(2) or ""
    args: dict = {}

    # Extraer argumentos clave-valor simples (ej: action='up', name='dolphin', query='...')
    arg_matches = re.findall(
        r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:['\"](.*?)['\"]|([a-zA-Z0-9_.-]+))",
        args_str,
    )
    for k, v_quoted, v_raw in arg_matches:
        raw = v_quoted if v_quoted != "" else v_raw
        if raw.isdigit():
            args[k] = int(raw)
        elif raw.lower() in ("true", "false"):
            args[k] = raw.lower() == "true"
        else:
            args[k] = raw

    # 1. Volumen / Audio
    if norm_name in ("volumecontrol", "setvolume", "audiocontrol", "soundcontrol"):
        action = args.get("action", "")
        direction = args.get("direction", "")
        if action == "mute":
            return "volume_control", {"action": "mute"}
        if action in ("up", "down"):
            return "volume_control", {"direction": action}
        if direction in ("up", "down"):
            return "volume_control", {"direction": direction}
        return "volume_control", {"direction": "up"}

    # 2. Control multimedia / Musica
    if norm_name in ("mediacontrol", "playbackcontrol", "musiccontrol"):
        action = args.get("action", "play_pause")
        return "media_control", {"action": action}

    # 3. Captura de pantalla y visualizacion de pantalla
    if norm_name in (
        "screenshot",
        "takescreenshot",
        "screenmonitor",
        "showscreen",
        "monitorscreen",
        "screen",
        "display",
        "verpantalla",
        "muestrapantalla",
        "pantallapc",
        "capturapantalla",
    ):
        return "screenshot", {}

    # 4. Terminal directo
    if norm_name in ("terminalcontrol", "terminal"):
        return "open_app", {"name": "terminal"}

    # 5. Apertura de aplicacion
    if norm_name in ("openapp", "launchapp", "appcontrol"):
        name = args.get("name") or args.get("app_name") or args.get("target", "")
        return "open_app", {"name": name}

    # 6. Busqueda web
    if norm_name in ("websearch", "searchweb", "browsercontrol"):
        query = args.get("query", "")
        return "web_search", {"query": query}

    # 7. Si el LLM emitio directamente TOOL: <nombre_app> (ej: TOOL: feishin o TOOL: dolphin)
    from jota.config import APP_ALIASES, CUSTOM_APP_MAPPINGS
    if norm_name in APP_ALIASES or norm_name in CUSTOM_APP_MAPPINGS:
        return "open_app", {"name": raw_tool_name}

    # 8. Control del telefono Android
    if norm_name in ("phonecontrol", "mobilecontrol", "phonetool", "celular", "phone"):
        action = args.get("action", "ring")
        value = args.get("value") or args.get("text") or args.get("url", "")
        return "phone_control", {"action": action, "value": value}

    # 9. Control de sesion y energia del PC
    if norm_name in ("lockpc", "lockscreen", "bloquearpc"):
        return "lock_pc", {}

    if norm_name in ("systempower", "powercontrol", "energiacontrol"):
        action = args.get("action", "suspend")
        confirmed = args.get("confirmed", False)
        return "system_power", {"action": action, "confirmed": confirmed}

    # 10. Gestion de ventanas
    if norm_name in (
        "closewindow",
        "closeactivewindow",
        "killwindow",
        "cerrarventana",
        "cerrarventanactiva",
    ):
        return "close_active_window", {}

    # 11. Notificaciones de escritorio
    if norm_name in (
        "sendnotification",
        "senddesktopnotification",
        "desktopnotification",
        "notificacion",
    ):
        title = args.get("title", "Jota")
        message = args.get("message") or args.get("text", "")
        return "send_notification", {"title": title, "message": message}

    # 12. Resumen del estado del PC
    if norm_name in ("pcsummary", "pcstatus", "estadopc", "systemsummary"):
        return "pc_summary", {}

    # 13. Gestion de workspaces de Hyprland
    if norm_name in (
        "switchworkspace",
        "changeworkspace",
        "cambiarescritorio",
        "iralescritorio",
        "workspace",
        "escritorio",
        "pasarescritorio",
        "pasadescritorio",
    ):
        raw_target = args.get("target") or args.get("workspace_id") or args.get("id", 1)
        try:
            target = int(raw_target)
        except (ValueError, TypeError):
            target = 1
        return "switch_workspace", {"target": target}

    if norm_name in ("movetoworkspace", "moveraescritorio", "movewindowworkspace"):
        raw_target = args.get("target") or args.get("workspace_id") or args.get("id", 1)
        app = args.get("app") or args.get("name") or args.get("app_name", "")
        try:
            target = int(raw_target)
        except (ValueError, TypeError):
            target = 1
        res_dict = {"target": target}
        if app:
            res_dict["app"] = app
        return "move_to_workspace", res_dict



    # 14. Clima y meteorologia
    if norm_name in ("getweather", "weather", "clima", "tiempo", "consultartiempo"):
        city_raw = args.get("city") or args.get("location") or args.get("ciudad", "Madrid")
        cleaned = re.sub(
            r"^(en|de|para|una|el|la)\s+", "", str(city_raw).strip(), flags=re.IGNORECASE
        ).strip()
        city = cleaned if cleaned else "Madrid"
        return "get_weather", {"city": city}

    # 15. Notas y recordatorios
    if norm_name in (
        "managenotes",
        "addnote",
        "anotarnota",
        "guardarnota",
        "listnotes",
        "leernotas",
        "clearnotes",
    ):
        action = args.get("action", "add")
        text = args.get("text") or args.get("content", "")
        return "manage_notes", {"action": action, "text": text}

    # 16. Temporizadores y alarmas
    if norm_name in ("settimer", "timer", "temporizador", "alarma", "recordatorio"):
        seconds = int(args.get("seconds") or (int(args.get("minutes", 0)) * 60) or 60)
        label = args.get("label", "temporizador")
        return "set_timer", {"seconds": seconds, "label": label}

    # 17. Hora y fecha del sistema
    if norm_name in ("getcurrenttime", "currenttime", "time", "hora", "fechahora", "date"):
        mode = args.get("mode", "time")
        return "get_current_time", {"mode": mode}

    # 18. Bateria del PC
    if norm_name in ("getpcbattery", "pcbattery", "bateriapc", "bateriaordenador", "battery"):
        return "get_pc_battery", {}

    # 19. Cancion que suena (Now playing)
    if norm_name in ("getnowplaying", "nowplaying", "cancionactual", "musicaactual", "quesuena"):
        return "get_now_playing", {}

    # 20. Cancelar temporizadores
    if norm_name in ("canceltimer", "stoptimer", "cancelartemporizador", "parartemporizador"):
        return "cancel_timer", {}

    # 21. Vision y analisis de pantalla
    if norm_name in ("analyzescreen", "screenvision", "vision", "explainscreen", "analizarpantalla"):
        question = args.get("question") or args.get("query", "Que hay en pantalla?")
        return "analyze_screen", {"question": question}

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

    if tool_name == "get_now_playing":
        from jota.tools.media import get_now_playing
        return get_now_playing()

    if tool_name == "open_app":
        name = args.get("name", "")
        return launch_application(name)

    if tool_name == "web_search":
        query = args.get("query", "")
        return open_web_search(query)

    if tool_name == "phone_control":
        from jota.tools.phone import phone_control
        action = args.get("action", "ring")
        value = args.get("value", "")
        msg = phone_control(action, value)
        return True, msg

    if tool_name == "lock_pc":
        from jota.tools.system import lock_pc
        return lock_pc()

    if tool_name == "system_power":
        from jota.tools.system import system_power
        action = args.get("action", "suspend")
        confirmed = bool(args.get("confirmed", False))
        return system_power(action, confirmed=confirmed)

    if tool_name == "close_active_window":
        from jota.tools.system import close_active_window
        return close_active_window()

    if tool_name == "send_notification":
        from jota.tools.system import send_desktop_notification
        return send_desktop_notification(
            args.get("title", "Jota"),
            args.get("message", "Aviso"),
        )

    if tool_name == "pc_summary":
        from jota.tools.system import get_pc_summary
        return get_pc_summary()

    if tool_name == "get_pc_battery":
        from jota.tools.system import get_pc_battery
        return get_pc_battery()

    if tool_name == "switch_workspace":
        from jota.tools.workspace import switch_workspace
        target = args.get("target", 1)
        return switch_workspace(target)

    if tool_name == "move_to_workspace":
        from jota.tools.workspace import move_to_workspace
        target = args.get("target", 1)
        app = args.get("app") or args.get("name") or args.get("app_name", "")
        return move_to_workspace(target, app)


    if tool_name == "get_weather":
        from jota.tools.weather import get_weather
        city = args.get("city", "Madrid")
        return get_weather(city)

    if tool_name == "manage_notes":
        from jota.tools.notes import add_note, clear_notes, list_notes, search_notes
        action = args.get("action", "add")
        if action in ("list", "leer", "consultar"):
            return list_notes(limit=int(args.get("limit", 5)))
        if action in ("clear", "borrar"):
            return clear_notes()
        if action in ("search", "buscar"):
            return search_notes(args.get("query") or args.get("text", ""))
        return add_note(args.get("text", ""))

    if tool_name == "set_timer":
        from jota.tools.timer import set_timer
        seconds = int(args.get("seconds", 60))
        label = args.get("label", "temporizador")
        return set_timer(seconds, label)

    if tool_name == "cancel_timer":
        from jota.tools.timer import cancel_timers
        return cancel_timers()

    if tool_name == "get_current_time":
        from jota.tools.datetime_tool import get_current_time
        mode = args.get("mode", "time")
        return get_current_time(mode)

    if tool_name == "analyze_screen":
        from jota.tools.screen_vision import analyze_screen
        question = args.get("question", "Que hay en pantalla?")
        return analyze_screen(question)

    return False, f"Herramienta no implementada: {tool_name}"


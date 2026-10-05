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

    # Confusiones de verbos de cierre (fonetica de Whisper)
    clean = re.sub(r"\b(fiera|fierra|sierra|cierre|cerra)\b", "cierra", clean)

    # Confusiones de verbos de volumen (fonetica de Whisper)
    clean = re.sub(r"\b(suelva|suelvo|suelba|suelbo|suelve)\b", "sube", clean)
    clean = re.sub(r"\b(bajame|bajale|bajalo)\b", "baja", clean)
    clean = re.sub(r"\b(subeme|subele|subelo)\b", "sube", clean)

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
    # 2a. Nivel especifico de volumen (ej: 'suelvo el volumen a 100', 'sube el volumen al 50%')
    vol_set = re.search(
        r"^(?:sube|subir|baja|bajar|pon|poner|coloca|colocar|ajusta|ajustar|establece|deja)?\s*"
        r"(?:el\s+)?(?:volumen|sonido|audio)\s+(?:al?|en)\s+(\d{1,3})\s*(?:%|por\s*ciento)?$"
        r"|^(?:sube|subir|baja|bajar|pon|poner|coloca|ajusta)\s+(?:el\s+)?(?:volumen|sonido|audio)\s+(\d{1,3})\s*(?:%|por\s*ciento)?$"
        r"|^(?:volumen|sonido|audio)\s+(?:al?|en)?\s*(\d{1,3})\s*(?:%|por\s*ciento)?$",
        clean,
    )
    if vol_set:
        val = vol_set.group(1) or vol_set.group(2) or vol_set.group(3)
        return "volume_control", {"action": "set", "level": int(val)}

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
    # 3a. Pausa
    if re.search(
        r"^(pausa|pausar|para|parar|deten|detener|corta|cortar)"
        r"(\s+(la\s+|el\s+)?(m[uú]sica|canci[oó]n|reproducci[oó]n|audio|pista|tema))?$",
        clean,
    ):
        return "media_control", {"action": "pause"}

    # 3b. Siguiente cancion / pista
    # (se evalua antes de play para comandos como 'reproduce la siguiente cancion')
    if re.search(
        r"^(reproduce\s+(la\s+)?|pon\s+(la\s+)?|pasa\s+(a\s+la\s+)?|salta\s+(a\s+la\s+)?)?"
        r"(siguiente|otra)\s+(canci[oó]n|pista|m[uú]sica|tema)"
        r"|^(cambia|pasa|salta)\s+(de\s+)?(canci[oó]n|pista|tema)"
        r"|^(pon\s+la\s+|pasa\s+a\s+la\s+)?siguiente(\s+canci[oó]n|\s+pista|\s+tema)?$"
        r"|^siguiente$",
        clean,
    ):
        return "media_control", {"action": "next"}

    # 3c. Cancion anterior / pista anterior
    if re.search(
        r"^(reproduce\s+(la\s+)?|pon\s+(la\s+)?|vuelve\s+a\s+la\s+|pasa\s+a\s+la\s+)?"
        r"(anterior|previa)\s+(canci[oó]n|pista|m[uú]sica|tema)"
        r"|^(canci[oó]n|pista|tema)\s+(anterior|previa)"
        r"|^(vuelve\s+a\s+la\s+|pon\s+la\s+)?anterior(\s+canci[oó]n|\s+pista|\s+tema)?$"
        r"|^anterior$",
        clean,
    ):
        return "media_control", {"action": "previous"}

    # 3d. Iniciar reproduccion / reanudar
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
        reserved_app_prefixes = (
            "brillo",
            "filtro",
            "modo noche",
            "luz nocturna",
            "esta ventana",
            "la ventana",
            "ventana",
            "contenedor",
            "puerto",
        )
        if not any(app_target.startswith(p) for p in reserved_app_prefixes):
            return "open_app", {"name": app_target}


    # 5b. Nombre directo de aplicacion o alias conocido
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
        generic_tokens = (
            "ventana", "aplicacion", "aplicación", "app", "la ventana", "la app", "el", "la"
        )
        if raw_app in generic_tokens:
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

    # 15. Verificacion de paquetes y software en el sistema
    reserved_pkg_words = {
        "cancion", "canción", "musica", "música", "volumen", "pantalla",
        "alarma", "temporizador", "nota", "notas", "terminal", "tiempo", "clima"
    }

    pkg_version_match = re.search(
        r"^(?:cual\s+es\s+la\s+|que\s+)?versi[oó]n\s+(?:de\s+|del\s+)?([a-zA-Z0-9_+.-]+)"
        r"(?:\s+del\s+sistema|\s+tengo|\s+hay)?$",
        clean,
    )
    if pkg_version_match:
        pkg = pkg_version_match.group(1).strip()
        if pkg not in reserved_pkg_words:
            return "check_package", {"name": pkg, "check": "version"}

    pkg_install_match = re.search(
        r"^(?:esta|est[aá]|tengo|hay)\s+([a-zA-Z0-9_+.-]+)(?:\s+instalad[oa])?\s+"
        r"(?:en\s+el\s+sistema|en\s+el\s+pc|en\s+mi\s+equipo)$"
        r"|^(?:esta|est[aá]|tengo|hay)\s+([a-zA-Z0-9_+.-]+)\s+instalad[oa]$"
        r"|^(?:esta|est[aá])\s+instalad[oa]\s+([a-zA-Z0-9_+.-]+)(?:\s+en\s+el\s+sistema|\s+en\s+el\s+pc)?$"
        r"|^which\s+([a-zA-Z0-9_+.-]+)$",
        clean,
    )
    if pkg_install_match:
        pkg = (
            pkg_install_match.group(1)
            or pkg_install_match.group(2)
            or pkg_install_match.group(3)
            or pkg_install_match.group(4)
        ).strip()
        if pkg not in reserved_pkg_words:
            return "check_package", {"name": pkg, "check": "installed"}

    # 16. Manipulacion de ventanas (pantalla completa, flotante, pin, centrar)
    if re.search(
        r"^(?:pon\s+(?:esta\s+)?ventana\s+en\s+pantalla\s+completa|pantalla\s+completa|"
        r"maximiza(?:r)?\s+(?:la\s+)?ventana|quita(?:r)?\s+(?:la\s+)?pantalla\s+completa)$",
        clean,
    ):
        return "window_action", {"action": "fullscreen"}

    if re.search(
        r"^(?:haz\s+flotante\s+(?:esta\s+)?ventana|ventana\s+flotante|"
        r"devuelve\s+(?:la\s+)?ventana\s+al\s+mosaico|pon\s+(?:la\s+)?ventana\s+en\s+mosaico|"
        r"modo\s+flotante|alterna(?:r)?\s+flotante)$",
        clean,
    ):
        return "window_action", {"action": "float"}

    if re.search(
        r"^(?:fija(?:r)?|ancla(?:r)?)\s+(?:esta\s+)?ventana"
        r"(?:\s+en\s+todos\s+los\s+escritorios)?$",
        clean,
    ):
        return "window_action", {"action": "pin"}

    if re.search(r"^(?:centra(?:r)?\s+(?:esta\s+)?ventana|centrar\s+ventana)$", clean):
        return "window_action", {"action": "center"}

    # 16b. Cierre de ventanas o aplicaciones especificas
    if re.search(
        r"^(?:cierra|cerrar|quitar|quita)\s+(?:esta\s+|la\s+)?ventana(?:\s+activa)?$",
        clean,
    ):
        return "close_window", {"app": ""}

    close_app_match = re.search(
        r"^(?:cierra|cerrar|quitar|quita)\s+"
        r"(?:(?:la\s+)?(?:ventana|aplicaci[oó]n|app)\s+(?:de\s+)?)?"
        r"(?:el\s+|la\s+|los\s+|las\s+)?"
        r"(.+)$",
        clean,
    )
    if close_app_match:
        target_raw = close_app_match.group(1).strip()
        reserved_close = {
            "ventana", "esta ventana", "la ventana", "esta", "activa",
            "sesion", "sesión", "el pc", "pc", "equipo", "ordenador",
            "temporizador", "alarma",
        }
        if target_raw not in reserved_close and not target_raw.startswith("sesion"):
            return "close_window", {"app": target_raw}

    # 17. Enfoque directo de ventanas / aplicaciones abiertas
    reserved_focus_words = {
        "pantalla", "escritorio", "musica", "música", "volumen", "nota", "notas",
        "tiempo", "clima", "brillo", "noche", "luz"
    }
    focus_match = re.search(
        r"^(?:pasa|ve|cambia|salta|enfoca|ir)\s+(?:a|al|a\s+la|el|la)?\s*([a-zA-Z0-9_+.-]+)"
        r"(?:\s+abiert[oa])?$",
        clean,
    )
    if focus_match:
        target_app = focus_match.group(1).strip()
        if target_app.lower() not in reserved_focus_words:
            return "focus_app", {"name": target_app}

    # 18. Control de brillo
    br_set_match = re.search(
        r"^(?:pon\s+el\s+brillo(?:\s+de\s+la\s+pantalla)?\s+al|brillo\s+al)\s+(\d+)\s*%?$",
        clean,
    )
    if br_set_match:
        return "brightness_control", {"percent": int(br_set_match.group(1)), "action": "set"}

    if re.search(r"^(?:sube|aumenta|mas)\s+(?:el\s+)?brillo(?:\s+de\s+la\s+pantalla)?$", clean):
        return "brightness_control", {"action": "up"}

    if re.search(r"^(?:baja|reduce|menos)\s+(?:el\s+)?brillo(?:\s+de\s+la\s+pantalla)?$", clean):
        return "brightness_control", {"action": "down"}

    if re.search(
        r"^(?:que\s+brillo\s+tengo|nivel\s+de\s+brillo|cuanto\s+brillo\s+tengo)$", clean
    ):
        return "brightness_control", {"action": "get"}

    # 19. Filtro de luz azul / modo noche
    if re.search(
        r"^(?:activa|activar|pon|poner|inicia|iniciar)\s+(?:el\s+)?"
        r"(?:filtro\s+de\s+luz\s+azul|modo\s+noche|luz\s+nocturna)$",
        clean,
    ):
        return "night_mode_control", {"action": "on"}

    if re.search(
        r"^(?:desactiva|desactivar|quita|quitar|apaga|apagar|para|parar)\s+(?:el\s+)?"
        r"(?:filtro\s+de\s+luz\s+azul|modo\s+noche|luz\s+nocturna)$",
        clean,
    ):
        return "night_mode_control", {"action": "off"}

    if re.search(
        r"^(?:cambia|cambiar|alterna|alternar|toggle)\s+(?:el\s+)?"
        r"(?:filtro\s+de\s+luz\s+azul|modo\s+noche|luz\s+nocturna)$",
        clean,
    ):
        return "night_mode_control", {"action": "toggle"}

    # 20. Inspeccion y liberacion de puertos
    m_port_kill = re.search(
        r"^(?:libera|liberar|mata|matar|cierra|cerrar)\s+"
        r"(?:lo\s+que\s+est[eé]\s+en\s+)?(?:el\s+)?puerto\s+(\d+)$",
        clean,
    )
    if m_port_kill:
        return "port_action", {"port": int(m_port_kill.group(1)), "action": "kill"}

    m_port_check = re.search(
        r"^(?:que\s+proceso\s+(?:esta\s+)?usa(?:ndo)?|quien\s+(?:esta\s+)?usa(?:ndo)?|"
        r"que\s+hay\s+en)\s+(?:el\s+)?puerto\s+(\d+)$"
        r"|^puerto\s+(\d+)$",
        clean,
    )
    if m_port_check:
        p = m_port_check.group(1) or m_port_check.group(2)
        return "port_action", {"port": int(p), "action": "check"}

    # 21. Gestion de contenedores (Docker / Podman)
    if re.search(
        r"^(?:que\s+contenedores\s+(?:estan\s+corriendo|hay)|"
        r"contenedores\s+(?:activos|en\s+ejecuci[oó]n)|"
        r"lista\s+de\s+contenedores|estado\s+de\s+(?:los\s+)?contenedores)$",
        clean,
    ):
        return "container_action", {"action": "list"}

    m_cont_stop = re.search(
        r"^(?:para|parar|deten|detener)\s+el\s+contenedor(?:\s+de)?\s+([a-zA-Z0-9_.-]+)$",
        clean,
    )
    if m_cont_stop:
        return "container_action", {"action": "stop", "target": m_cont_stop.group(1)}

    m_cont_restart = re.search(
        r"^(?:reinicia|reiniciar)\s+el\s+contenedor(?:\s+de)?\s+([a-zA-Z0-9_.-]+)$",
        clean,
    )
    if m_cont_restart:
        return "container_action", {"action": "restart", "target": m_cont_restart.group(1)}

    m_cont_start = re.search(
        r"^(?:inicia|iniciar|arranca|arrancar)\s+el\s+contenedor(?:\s+de)?\s+([a-zA-Z0-9_.-]+)$",
        clean,
    )
    if m_cont_start:
        return "container_action", {"action": "start", "target": m_cont_start.group(1)}

    # 22. Monitor de consumo (RAM / CPU) y matar procesos
    if re.search(
        r"^(?:que\s+proceso\s+(?:(?:esta\s+)?(?:consumiendo|consume)|usa|gasta)\s+m[aá]s\s+"
        r"(?:ram|memoria)|procesos\s+con\s+m[aá]s\s+(?:ram|memoria)|uso\s+de\s+memoria|"
        r"que\s+consume\s+m[aá]s\s+(?:ram|memoria))$",
        clean,
    ):
        return "process_monitor", {"action": "top_ram"}

    if re.search(
        r"^(?:que\s+proceso\s+(?:(?:esta\s+)?(?:consumiendo|consume)|se\s+esta\s+comiendo|"
        r"usa|gasta)\s+(?:la\s+|m[aá]s\s+)?cpu|procesos\s+con\s+m[aá]s\s+cpu|"
        r"quien\s+consume\s+(?:m[aá]s\s+)?cpu|que\s+consume\s+m[aá]s\s+cpu)$",
        clean,
    ):
        return "process_monitor", {"action": "top_cpu"}

    m_kill_proc = re.search(
        r"^(?:mata|matar|termina|terminar)\s+(?:el\s+proceso\s+)?(?:con\s+pid\s+)?(\d+)$"
        r"|^(?:mata|matar|termina|terminar)\s+el\s+proceso\s+(?:colgado\s+de\s+|de\s+)?"
        r"([a-zA-Z0-9_.-]+)$",
        clean,
    )
    if m_kill_proc:
        target = m_kill_proc.group(1) or m_kill_proc.group(2)
        return "kill_process", {"target": target}

    # 23. Estado de repositorio Git
    if re.search(
        r"^(?:c[oó]mo\s+est[aá]\s+el\s+repo(?:sitorio)?(?:\s+actual)?|"
        r"tengo\s+cambios\s+sin\s+(?:commitear|confirmar)|"
        r"estado\s+del\s+repo(?:sitorio)?|estado\s+de\s+git|git\s+status)$",
        clean,
    ):
        return "git_status", {}

    # 24. PC-to-Mobile: Captura de pantalla, URL y archivos al telefono
    m_ws_shot = re.search(
        r"^(?:manda|mandar|envia|enviar|pasa|pasar)\s+(?:una\s+)?captura(?:\s+de\s+pantalla)?\s+"
        r"(?:del\s+|de\s+)?(?:espacio|workspace)\s+(\d+)\s+al\s+(?:m[oó]vil|tel[eé]fono|celular)$",
        clean,
    )
    if m_ws_shot:
        return "phone_send_screenshot", {"workspace": int(m_ws_shot.group(1))}

    if re.search(
        r"^(?:manda|mandar|envia|enviar|pasa|pasar)\s+"
        r"(?:(?:una\s+)?captura(?:\s+de\s+pantalla)?|la\s+pantalla)\s+"
        r"al\s+(?:m[oó]vil|tel[eé]fono|celular)$",
        clean,
    ):
        return "phone_send_screenshot", {}

    m_url = re.search(
        r"^(?:manda|mandar|envia|enviar|pasa|pasar)\s+(?:la\s+url|el\s+enlace|el\s+link)\s+"
        r"(https?://\S+)\s+al\s+(?:m[oó]vil|tel[eé]fono|celular)$",
        clean,
    )
    if m_url:
        return "phone_send_url", {"url": m_url.group(1)}

    if re.search(
        r"^(?:manda|mandar|envia|enviar|pasa|pasar)\s+"
        r"(?:la\s+url|este\s+enlace|el\s+enlace|el\s+link|esta\s+p[aá]gina)\s+"
        r"al\s+(?:m[oó]vil|tel[eé]fono|celular)$"
        r"|^(?:abre|abrir)\s+esta\s+p[aá]gina\s+en\s+el\s+(?:m[oó]vil|tel[eé]fono|celular)$",
        clean,
    ):
        return "phone_send_url", {}

    if re.search(
        r"^(?:manda|mandar|envia|enviar|pasa|pasar)\s+"
        r"(?:este\s+archivo|el\s+archivo\s+seleccionado|este\s+documento)\s+"
        r"al\s+(?:m[oó]vil|tel[eé]fono|celular)$",
        clean,
    ):
        return "phone_send_file", {"target": ""}

    m_file = re.search(
        r"^(?:manda|mandar|envia|enviar|pasa|pasar)\s+el\s+archivo\s+(.+)\s+"
        r"al\s+(?:m[oó]vil|tel[eé]fono|celular)$",
        clean,
    )
    if m_file:
        return "phone_send_file", {"target": m_file.group(1).strip()}

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
        level = args.get("level") or args.get("value")
        if level is not None:
            return "volume_control", {"action": "set", "level": int(level)}
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

    # 10. Gestion y cierre de ventanas
    if norm_name in (
        "closewindow",
        "closeactivewindow",
        "killwindow",
        "cerrarventana",
        "cerrarventanactiva",
        "close",
    ):
        app = (
            args.get("app")
            or args.get("name")
            or args.get("app_name")
            or args.get("target", "")
        )
        if norm_name in ("closeactivewindow", "cerrarventanactiva") and not app:
            return "close_active_window", {}
        return "close_window", {"app": app}


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
    if norm_name in (
        "analyzescreen", "screenvision", "vision", "explainscreen", "analizarpantalla"
    ):
        question = args.get("question") or args.get("query", "Que hay en pantalla?")
        return "analyze_screen", {"question": question}

    # 22. Verificacion de paquetes y software en el sistema
    if norm_name in (
        "checkpackage", "packagecheck", "whichpackage", "packageversion",
        "versioncheck", "checkversion", "isinstalled", "which", "package", "paquete"
    ):
        name = args.get("name") or args.get("package") or args.get("target", "")
        default_check = "installed" if norm_name in ("which", "isinstalled") else "version"
        check = args.get("check") or args.get("type") or args.get("action") or default_check
        return "check_package", {"name": name, "check": check}

    # 23. Manipulacion de ventanas (fullscreen, float, pin, center)
    if norm_name in ("windowaction", "window", "manipulatewindow", "ventana"):
        action = args.get("action") or args.get("mode", "fullscreen")
        return "window_action", {"action": action}

    # 24. Enfoque de aplicaciones abiertas
    if norm_name in ("focusapp", "focuswindow", "focus", "enfocar", "saltaraapp"):
        name = args.get("name") or args.get("app") or args.get("target", "")
        return "focus_app", {"name": name}

    # 25. Control de brillo de pantalla
    if norm_name in ("brightnesscontrol", "brightness", "setbrightness", "brillo"):
        percent = args.get("percent") or args.get("level") or args.get("pct")
        action = args.get("action", "set" if percent is not None else "get")
        res_args: dict = {"action": action}
        if percent is not None:
            res_args["percent"] = percent
        return "brightness_control", res_args

    # 26. Modo noche / filtro de luz azul
    if norm_name in ("nightmodecontrol", "nightmode", "modonoche", "bluelight", "luzazul"):
        action = args.get("action", "toggle")
        return "night_mode_control", {"action": action}

    # 27. Gestion e inspeccion de puertos
    if norm_name in ("portaction", "portcontrol", "port", "puerto", "checkport", "killport"):
        raw_port = args.get("port") or args.get("number") or 80
        action = args.get("action", "check")
        if norm_name == "killport":
            action = "kill"
        if norm_name == "checkport":
            action = "check"
        try:
            port = int(raw_port)
        except (ValueError, TypeError):
            port = 80
        return "port_action", {"port": port, "action": action}

    # 28. Gestion de contenedores Docker / Podman
    if norm_name in (
        "containeraction",
        "containercontrol",
        "container",
        "contenedor",
        "docker",
        "podman",
    ):
        action = args.get("action", "list")
        target = args.get("target") or args.get("name") or args.get("container", "")
        return "container_action", {"action": action, "target": target}

    # 29. Monitor de procesos (CPU / RAM)
    if norm_name in (
        "processmonitor",
        "processresourcemonitor",
        "topcpu",
        "topram",
        "procesos",
        "monitorprocesos",
    ):
        action = args.get("action", "top_cpu")
        if norm_name == "topram":
            action = "top_ram"
        if norm_name == "topcpu":
            action = "top_cpu"
        return "process_monitor", {"action": action}

    # 30. Terminar proceso
    if norm_name in ("killprocess", "terminateprocess", "matarproceso", "cerrarproceso"):
        target = args.get("target") or args.get("pid") or args.get("name") or ""
        return "kill_process", {"target": str(target)}

    # 31. Estado de repositorio Git
    if norm_name in ("gitstatus", "git", "repostatus", "estadorepo", "repocontrol"):
        path = args.get("path") or args.get("repo", "")
        return "git_status", {"path": str(path)}

    # 32. PC-to-Mobile (Capturas, archivos y URLs al telefono)
    if norm_name in (
        "phonesendscreenshot",
        "sendscreenshottophone",
        "capturamovil",
        "mandarcapturaalmovil",
    ):
        raw_ws = args.get("workspace") or args.get("target") or args.get("id")
        ws = int(raw_ws) if raw_ws is not None else None
        res_ws = {}
        if ws is not None:
            res_ws["workspace"] = ws
        return "phone_send_screenshot", res_ws

    if norm_name in (
        "phonesendurl",
        "sendurltophone",
        "urlmovil",
        "mandarenlacealmovil",
        "abrirurlmovil",
    ):
        url = args.get("url") or args.get("link") or ""
        return "phone_send_url", {"url": str(url)}

    if norm_name in (
        "phonesendfile",
        "sendfiletophone",
        "archivomovil",
        "mandararchivoalmovil",
        "enviararchivoalmovil",
    ):
        target = args.get("target") or args.get("name") or args.get("file") or ""
        return "phone_send_file", {"target": str(target)}

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
        if args.get("action") == "set" or "level" in args:
            from jota.tools.media import set_volume_level
            level = int(args.get("level", 50))
            return set_volume_level(level)
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

    if tool_name in ("close_window", "close_active_window"):
        from jota.tools.workspace import close_window

        app = args.get("app") or args.get("name") or args.get("app_name", "")
        return close_window(app_name=app)


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

    if tool_name == "check_package":
        from jota.tools.packages import check_package
        name = args.get("name") or args.get("package") or args.get("target", "")
        check = args.get("check") or args.get("action") or "version"
        return check_package(name=name, check=check)

    if tool_name == "window_action":
        from jota.tools.workspace import window_action
        action = args.get("action", "fullscreen")
        return window_action(action)

    if tool_name == "focus_app":
        from jota.tools.workspace import focus_app
        name = args.get("name") or args.get("app", "")
        return focus_app(name)

    if tool_name == "brightness_control":
        from jota.tools.display import brightness_control
        percent = args.get("percent")
        action = args.get("action", "set" if percent is not None else "get")
        return brightness_control(percent=percent, action=action)

    if tool_name == "night_mode_control":
        from jota.tools.display import night_mode_control
        action = args.get("action", "toggle")
        return night_mode_control(action=action)

    if tool_name == "port_action":
        from jota.tools.devops import port_action
        port = int(args.get("port", 80))
        action = args.get("action", "check")
        return port_action(port=port, action=action)

    if tool_name == "container_action":
        from jota.tools.devops import container_action
        action = args.get("action", "list")
        target = args.get("target") or args.get("name") or args.get("container", "")
        return container_action(action=action, target=target)

    if tool_name == "process_monitor":
        from jota.tools.devops import process_monitor_action
        action = args.get("action", "top_cpu")
        return process_monitor_action(action=action)

    if tool_name == "kill_process":
        from jota.tools.devops import kill_process_action
        target = args.get("target") or args.get("pid") or args.get("name", "")
        return kill_process_action(target=str(target))

    if tool_name == "git_status":
        from jota.tools.devops import git_status_action
        path = args.get("path") or args.get("repo", "")
        return git_status_action(path=str(path))

    if tool_name == "phone_send_screenshot":
        from jota.tools.phone import send_screenshot_to_phone
        return send_screenshot_to_phone(workspace=args.get("workspace"))

    if tool_name == "phone_send_url":
        from jota.tools.phone import send_active_url_to_phone
        return send_active_url_to_phone(url=args.get("url", ""))

    if tool_name == "phone_send_file":
        from jota.tools.phone import send_active_file_to_phone
        return send_active_file_to_phone(target=args.get("target", ""))

    return False, f"Herramienta no implementada: {tool_name}"




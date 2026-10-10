"""
Motor de ejecucion de escenas y rutinas YAML para Jota.
Permite ejecutar secuencias de herramientas complejas con un unico comando por voz.
"""

import logging
from typing import Any

import yaml

from jota.config import SCENES_FILE

logger = logging.getLogger(__name__)

DEFAULT_SCENES_YAML = """# Archivo de configuracion de escenas y rutinas para Jota
scenes:
  modo_cine:
    description: "Modo peliculas: pantalla completa, baja brillo y luz nocturna"
    actions:
      - tool: window_action
        args: { action: fullscreen }
      - tool: brightness_control
        args: { percent: 20 }
      - tool: night_mode_control
        args: { action: on }
      - tool: cec_control
        args: { action: turn_on }

  modo_trabajo:
    description: "Configura el entorno de desarrollo y productividad"
    actions:
      - tool: brightness_control
        args: { percent: 80 }
      - tool: night_mode_control
        args: { action: off }
      - tool: switch_workspace
        args: { target: 1 }

  buenas_noches:
    description: "Apaga pantallas, silencia audio y bloquea el equipo para descansar"
    actions:
      - tool: night_mode_control
        args: { action: on }
      - tool: volume_control
        args: { action: mute }
      - tool: cec_control
        args: { action: turn_off }
      - tool: lock_pc
        args: {}
"""


def ensure_scenes_file() -> dict[str, Any]:
    """Carga el archivo scenes.yaml o lo crea con valores por defecto si no existe."""
    if not SCENES_FILE.exists():
        try:
            SCENES_FILE.parent.mkdir(parents=True, exist_ok=True)
            SCENES_FILE.write_text(DEFAULT_SCENES_YAML, encoding="utf-8")
        except Exception as e:
            logger.warning("No se pudo escribir archivo de escenas por defecto: %s", e)
            return yaml.safe_load(DEFAULT_SCENES_YAML).get("scenes", {})

    try:
        content = SCENES_FILE.read_text(encoding="utf-8")
        data = yaml.safe_load(content) or {}
        return data.get("scenes", {})
    except Exception as e:
        logger.error("Error al parsear %s: %s", SCENES_FILE, e)
        return {}


def normalize_scene_name(name: str) -> str:
    """Normaliza el nombre de la escena eliminando articulos y espacios."""
    clean = name.lower().strip()
    clean = clean.replace(" ", "_").replace("-", "_")
    clean = clean.replace("á", "a").replace("é", "e").replace("í", "i")
    clean = clean.replace("ó", "o").replace("ú", "u")
    if clean.startswith("el_"):
        clean = clean[3:]
    return clean


def trigger_scene(name: str) -> tuple[bool, str]:
    """
    Ejecuta todas las acciones definidas en la escena indicada.
    Retorna (exito, mensaje_para_tts).
    """
    scenes = ensure_scenes_file()
    norm_target = normalize_scene_name(name)

    # Buscar coincidencia exacta o parcial
    target_scene = None
    matched_key = ""
    for key, sc in scenes.items():
        if normalize_scene_name(key) == norm_target or norm_target in normalize_scene_name(key):
            target_scene = sc
            matched_key = key
            break

    if not target_scene:
        avail = ", ".join(scenes.keys())
        return False, f"No encontre la escena '{name}'. Escenas disponibles: {avail}."

    actions = target_scene.get("actions", [])
    if not actions:
        return True, f"La escena '{matched_key}' no contiene ninguna accion definida."

    from jota.tools.router import execute_tool

    successes = 0
    errors = 0
    for act in actions:
        tool_name = act.get("tool")
        tool_args = act.get("args", {})
        if tool_name:
            try:
                ok, _ = execute_tool(tool_name, tool_args)
                if ok:
                    successes += 1
                else:
                    errors += 1
            except Exception as e:
                logger.error(
                    "Error ejecutando accion %s en escena %s: %s",
                    tool_name,
                    matched_key,
                    e,
                )
                errors += 1

    clean_title = matched_key.replace("_", " ")
    if errors == 0:
        return True, f"Escena {clean_title} activada correctamente."
    return True, f"Escena {clean_title} activada con {successes} acciones aplicadas."


def list_scenes() -> tuple[bool, str]:
    """Retorna un listado en texto de las escenas disponibles."""
    scenes = ensure_scenes_file()
    if not scenes:
        return True, "No hay ninguna escena configurada en el sistema."

    nombres = [k.replace("_", " ") for k in scenes.keys()]
    return True, f"Escenas configuradas: {', '.join(nombres)}."

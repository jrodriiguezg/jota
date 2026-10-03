"""Gestion y apertura de aplicaciones por nombre, MIME type o alias personalizados."""

import logging
import re
import shutil
import subprocess

from jota.config import APP_ALIASES, CUSTOM_APP_MAPPINGS, DEFAULT_MIME_TYPES

logger = logging.getLogger(__name__)


def _clean_app_query(query: str) -> str:
    """Limpia el texto de peticion para extraer el nombre o categoria de la app."""
    text = query.lower().strip()
    # Eliminar articulos y frases introductorias
    pattern = r"^(por favor\s+|puedes\s+)?(abrir|abre|lanza|lanzar|ejecuta|ejecutar)\s+"
    text = re.sub(pattern, "", text)
    text = re.sub(r"^(el|la|los|las|un|una)\s+", "", text)
    text = re.sub(r"\s+(por favor|porfa)$", "", text)
    return text.strip()


def resolve_mime_default(mime_type: str) -> str | None:
    """Consulta la aplicacion predeterminada para un MIME type usando xdg-mime."""
    if not shutil.which("xdg-mime"):
        return None

    try:
        proc = subprocess.run(
            ["xdg-mime", "query", "default", mime_type],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception as exc:
        logger.warning("Error al consultar xdg-mime para %s: %s", mime_type, exc)
    return None


def resolve_app_target(raw_target: str) -> tuple[str, str]:
    """
    Resuelve el objetivo pedido a un ID de aplicacion, comando o .desktop,
    junto con un nombre amigable para lectura TTS.
    Devuelve (target_lanzable, nombre_amigable).
    """
    clean = _clean_app_query(raw_target)

    # 1. Comprobar alias definidos
    if clean in APP_ALIASES:
        resolved = APP_ALIASES[clean]
        friendly = clean.capitalize()
    # 2. Comprobar mapeos personalizados
    elif clean in CUSTOM_APP_MAPPINGS:
        resolved = CUSTOM_APP_MAPPINGS[clean]
        friendly = clean.capitalize()
    # 3. Comprobar tipos MIME por defecto
    elif clean in DEFAULT_MIME_TYPES:
        resolved = DEFAULT_MIME_TYPES[clean]
        friendly = clean.replace("_", " ").capitalize()
    else:
        resolved = clean
        friendly = clean.capitalize()

    # Si es un MIME type (contiene '/'), resolver la aplicacion por defecto del sistema
    if "/" in resolved:
        desktop_id = resolve_mime_default(resolved)
        if desktop_id:
            resolved = desktop_id

    # Si termina en .desktop, se puede usar directamente con gtk-launch
    return resolved, friendly


def launch_application(target: str) -> tuple[bool, str]:
    """
    Lanza una aplicacion en segundo plano en el entorno de escritorio Wayland.
    Devuelve (exito, mensaje_para_tts).
    """
    resolved, friendly_name = resolve_app_target(target)
    logger.info("Intentando abrir aplicacion: %r (resuelto a %r)", target, resolved)

    desktop_id = resolved[:-8] if resolved.endswith(".desktop") else resolved

    # 1. Intentar con gtk-launch (soporta aplicaciones .desktop del sistema y Flatpak)
    if shutil.which("gtk-launch"):
        try:
            # Probar con el nombre sin extension y con extension
            proc = subprocess.run(
                ["gtk-launch", desktop_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=3,
            )
            if proc.returncode == 0:
                msg = f"Abriendo {friendly_name}."
                logger.info(msg)
                return True, msg
        except Exception as exc:
            logger.debug("gtk-launch fallo para %s: %s", desktop_id, exc)

    # 2. Si parece un Flatpak ID o existe en flatpak
    if resolved.startswith("org.") and shutil.which("flatpak"):
        try:
            subprocess.Popen(
                ["flatpak", "run", desktop_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            msg = f"Abriendo {friendly_name}."
            logger.info(msg)
            return True, msg
        except Exception as exc:
            logger.debug("flatpak run fallo para %s: %s", desktop_id, exc)

    # 3. Intentar como binario en PATH
    binary_path = shutil.which(desktop_id) or shutil.which(resolved)
    if binary_path:
        try:
            subprocess.Popen(
                [binary_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            msg = f"Abriendo {friendly_name}."
            logger.info(msg)
            return True, msg
        except Exception as exc:
            logger.error("Error al ejecutar binario %s: %s", binary_path, exc)

    # 4. Fallback con gio launch si esta disponible
    if shutil.which("gio"):
        try:
            # Buscar el archivo desktop en rutas estandar
            res = subprocess.run(
                ["gio", "launch", f"{desktop_id}.desktop"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=3,
            )
            if res.returncode == 0:
                msg = f"Abriendo {friendly_name}."
                return True, msg
        except Exception:
            pass

    err_msg = f"No pude encontrar ni abrir la aplicacion {friendly_name}."
    logger.warning(err_msg)
    return False, err_msg

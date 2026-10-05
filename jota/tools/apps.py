"""Gestion y apertura de aplicaciones por nombre, MIME type o alias personalizados."""

import logging
import re
import shutil
import subprocess

from jota.config import APP_ALIASES, CUSTOM_APP_MAPPINGS, DEFAULT_MIME_TYPES

logger = logging.getLogger(__name__)


def _clean_app_query(query: str) -> str:
    """Limpia y sanea el texto de peticion para extraer el nombre o categoria de la app."""
    # Eliminar metacaracteres peligrosos de inyeccion shell
    sanitized = re.sub(r"[;&|`$<>\n\r]", "", query)
    text = sanitized.lower().strip()
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
        # 4. Busqueda aproximada para tolerar fallos foneticos de STT
        import difflib

        close = difflib.get_close_matches(clean, APP_ALIASES.keys(), n=1, cutoff=0.7)
        if close:
            best_match = close[0]
            resolved = APP_ALIASES[best_match]
            friendly = best_match.capitalize()
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


def spawn_detached(cmd: list[str]) -> bool:
    """
    Ejecuta un comando totalmente desacoplado del ciclo de vida de Jota.
    Garantiza que la aplicacion permanezca abierta aunque Jota se cierre o reciba SIGINT.
    Prioridades:
    1. hyprctl dispatch hl.dsp.exec_cmd(...) (Hyprland 0.56+)
    2. hyprctl dispatch exec ... (Hyprland clasico)
    3. systemd-run --user --slice=app.slice ... (cgroup independiente de systemd)
    4. subprocess.Popen(..., start_new_session=True) (sesion POSIX desacoplada)
    """
    import shlex

    cmd_str = shlex.join(cmd)

    # 1. Delegar ejecucion en el compositor Wayland Hyprland
    hyprctl = shutil.which("hyprctl")
    if hyprctl:
        try:
            safe_str = cmd_str.replace("\\", "\\\\").replace("'", "\\'")
            res_lua = subprocess.run(
                [hyprctl, "dispatch", f"hl.dsp.exec_cmd('{safe_str}')"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if res_lua.returncode == 0 and "error" not in res_lua.stderr.lower():
                return True

            res_fb = subprocess.run(
                [hyprctl, "dispatch", "exec", cmd_str],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if res_fb.returncode == 0 and "error" not in res_fb.stderr.lower():
                return True
        except Exception as e:
            logger.debug("hyprctl dispatch exec no disponible: %s", e)

    # 2. Delegar en systemd user slice
    systemd_run = shutil.which("systemd-run")
    if systemd_run:
        try:
            res_sd = subprocess.run(
                [systemd_run, "--user", "--slice=app.slice", "--no-block", *cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=3,
            )
            if res_sd.returncode == 0:
                return True
        except Exception as e:
            logger.debug("systemd-run fallo: %s", e)

    # 3. Fallback directo con setsid / start_new_session
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except Exception as e:
        logger.error("Error al lanzar proceso desacoplado: %s", e)
        return False


def launch_application(target: str) -> tuple[bool, str]:
    """
    Lanza una aplicacion en segundo plano en el entorno de escritorio Wayland.
    Devuelve (exito, mensaje_para_tts).
    """
    resolved, friendly_name = resolve_app_target(target)
    logger.info("Intentando abrir aplicacion: %r (resuelto a %r)", target, resolved)

    desktop_id = resolved[:-8] if resolved.endswith(".desktop") else resolved

    # 1. Intentar con gtk-launch desacoplado (soporta aplicaciones .desktop del sistema y Flatpak)
    if shutil.which("gtk-launch"):
        if spawn_detached(["gtk-launch", desktop_id]):
            msg = f"Abriendo {friendly_name}."
            logger.info(msg)
            return True, msg

    # 2. Si parece un Flatpak ID o existe en flatpak
    if resolved.startswith("org.") and shutil.which("flatpak"):
        if spawn_detached(["flatpak", "run", desktop_id]):
            msg = f"Abriendo {friendly_name}."
            logger.info(msg)
            return True, msg

    # 3. Intentar como binario en PATH
    binary_path = shutil.which(desktop_id) or shutil.which(resolved)
    if binary_path:
        if spawn_detached([binary_path]):
            msg = f"Abriendo {friendly_name}."
            logger.info(msg)
            return True, msg

    # 4. Fallback con gio launch si esta disponible
    if shutil.which("gio"):
        if spawn_detached(["gio", "launch", f"{desktop_id}.desktop"]):
            msg = f"Abriendo {friendly_name}."
            return True, msg

    err_msg = f"No pude encontrar ni abrir la aplicacion {friendly_name}."
    logger.warning(err_msg)
    return False, err_msg

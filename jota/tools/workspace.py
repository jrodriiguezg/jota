"""Control de workspaces y ventanas en Hyprland."""

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


def switch_workspace(workspace_id: int | str) -> tuple[bool, str]:
    """Cambia el espacio de trabajo activo en Hyprland."""
    hyprctl = shutil.which("hyprctl")
    if not hyprctl:
        return False, "hyprctl no esta disponible en este entorno."

    target = str(workspace_id).strip()
    try:
        # Hyprland 0.56+ (sintaxis Lua hl.dsp)
        res = subprocess.run(
            [hyprctl, "dispatch", f"hl.dsp.focus({{ workspace = {target} }})"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and "error" not in res.stderr.lower():
            return True, f"Cambiado al espacio de trabajo {target}."

        # Fallback clasico Hyprland <0.56
        res_fallback = subprocess.run(
            [hyprctl, "dispatch", "workspace", target],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res_fallback.returncode == 0:
            return True, f"Cambiado al espacio de trabajo {target}."
        err_msg = res.stderr.strip() or res_fallback.stderr.strip()
        return False, f"Fallo al cambiar de espacio de trabajo: {err_msg}"
    except Exception as e:
        logger.error("Error al cambiar workspace: %s", e)
        return False, f"Error al cambiar espacio de trabajo: {e}"


def move_to_workspace(workspace_id: int | str, app_name: str = "") -> tuple[bool, str]:
    """
    Mueve una ventana al espacio de trabajo indicado.
    Si se especifica app_name, busca la ventana correspondiente en Hyprland y la mueve.
    Si no se especifica o no se encuentra, mueve la ventana activa en foco.
    """
    import json

    hyprctl = shutil.which("hyprctl")
    if not hyprctl:
        return False, "hyprctl no esta disponible en este entorno."

    target = str(workspace_id).strip()
    target_address: str | None = None
    friendly_found: str = ""

    # 1. Si se especifico un nombre de aplicacion, buscar entre los clientes de Hyprland
    clean_app = app_name.strip()
    if clean_app:
        from jota.tools.apps import resolve_app_target

        resolved_app, friendly_name = resolve_app_target(clean_app)
        search_terms = {
            clean_app.lower(),
            friendly_name.lower(),
            resolved_app.lower(),
        }
        if resolved_app.startswith("org."):
            search_terms.add(resolved_app.split(".")[-1].lower())

        try:
            clients_proc = subprocess.run(
                [hyprctl, "clients", "-j"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if clients_proc.returncode == 0 and clients_proc.stdout.strip():
                clients = json.loads(clients_proc.stdout)
                for client in clients:
                    c_class = (client.get("class") or "").lower()
                    c_init = (client.get("initialClass") or "").lower()
                    c_title = (client.get("title") or "").lower()
                    for term in search_terms:
                        if term and (term in c_class or term in c_init or term in c_title):
                            target_address = client.get("address")
                            friendly_found = friendly_name
                            break
                    if target_address:
                        break
        except Exception as e:
            logger.debug("Error al listar clientes de Hyprland: %s", e)

    try:
        # 2. Si se encontro la ventana por direccion, moverla especificamente
        if target_address:
            res = subprocess.run(
                [hyprctl, "dispatch", "movetoworkspace", f"{target},address:{target_address}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                name = friendly_found or clean_app.capitalize()
                return True, f"Ventana de {name} movida al espacio de trabajo {target}."

        # 3. Mover ventana activa
        # Hyprland 0.56+ (sintaxis Lua hl.dsp)
        res = subprocess.run(
            [hyprctl, "dispatch", f"hl.dsp.window.move({{ workspace = {target} }})"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and "error" not in res.stderr.lower():
            return True, f"Ventana movida al espacio de trabajo {target}."

        # Fallback clasico Hyprland <0.56
        res_fallback = subprocess.run(
            [hyprctl, "dispatch", "movetoworkspace", target],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res_fallback.returncode == 0:
            return True, f"Ventana movida al espacio de trabajo {target}."
        err_msg = res.stderr.strip() or res_fallback.stderr.strip()
        return False, f"Fallo al mover ventana: {err_msg}"
    except Exception as e:
        logger.error("Error al mover ventana a workspace: %s", e)
        return False, f"Error al mover ventana: {e}"


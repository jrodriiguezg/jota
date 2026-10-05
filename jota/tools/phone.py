"""
Herramienta de integracion con el telefono Android (Jota Bridge).
Permite al asistente controlar el dispositivo movil por voz:
hacerlo sonar, consultar su bateria y enviarle texto o enlaces.
"""

import asyncio
import json
import logging
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from bridge.config import BRIDGE_API_KEY, BRIDGE_PORT, BRIDGE_TEMP_DIR
from bridge.pc_ops import resolve_safe_file_path
from bridge.phone_manager import phone_manager

logger = logging.getLogger(__name__)


def phone_control(action: str, value: str = "") -> str:
    """
    Ejecuta una accion sobre el telefono Android vinculado.
    Acciones soportadas:
        - 'ring': Hace sonar el telefono al maximo volumen y vibra.
        - 'status': Consulta la bateria y estado del telefono.
        - 'clipboard': Envia texto al portapapeles del telefono.
        - 'open_url': Abre una URL en el navegador del telefono.
    """
    clean_action = action.lower().strip()
    logger.info("phone_control llamado: accion='%s', valor=%r", clean_action, value)

    # 1. Intentar directamente en memoria si el bridge corre en el mismo proceso
    if phone_manager.is_connected():
        return _execute_in_process(clean_action, value)

    # 2. Si no esta en el mismo proceso, consultar el demonio local del bridge via HTTP
    return _execute_via_http(clean_action, value)


def _resolve_file_for_phone(query: str) -> Path | None:
    """Localiza un archivo del PC solicitado para enviar al telefono."""
    clean = query.strip()
    if not clean:
        return None

    # Caso especial: capturas de pantalla
    if any(k in clean.lower() for k in ("captura", "screenshot", "pantalla")):
        candidates: list[Path] = []
        for base in [
            Path.home() / "Imágenes" / "Capturas",
            Path.home() / "Pictures" / "Screenshots",
            Path.home() / "Imágenes",
            Path.home() / "Pictures",
            BRIDGE_TEMP_DIR,
        ]:
            if base.exists():
                candidates.extend(base.glob("*.png"))
                candidates.extend(base.glob("*.jpg"))
        if candidates:
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return candidates[0]

        from jota.tools.screenshot import take_screenshot_to_clipboard
        take_screenshot_to_clipboard()
        for base in [Path.home() / "Imágenes", BRIDGE_TEMP_DIR]:
            if base.exists():
                candidates.extend(base.glob("*.png"))
        if candidates:
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return candidates[0]

    # Intentar resolver como ruta segura directa
    try:
        p = resolve_safe_file_path(clean)
        if p.is_file():
            return p
    except Exception:
        pass

    # Buscar por coincidencia de nombre en Descargas o Documentos
    for folder in [
        Path.home() / "Descargas",
        Path.home() / "Downloads",
        Path.home() / "Documentos",
        Path.home(),
    ]:
        if folder.exists():
            matches = [m for m in folder.glob(f"*{clean}*") if m.is_file()]
            if matches:
                matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                return matches[0]

    return None


def _execute_in_process(action: str, value: str) -> str:
    """Ejecucion directa usando el PhoneConnectionManager en memoria."""
    loop = None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        pass

    if action in ("ring", "sonar", "alarma"):
        coro = phone_manager.ring_phone()
        if loop and loop.is_running():
            asyncio.create_task(coro)
        else:
            asyncio.run(coro)
        return "Haciendo sonar tu telefono."

    if action in ("torch", "linterna", "flash"):
        state = value.lower().strip() not in ("off", "apagar", "false", "0", "desactivar")
        coro = phone_manager.set_torch(state)
        if loop and loop.is_running():
            asyncio.create_task(coro)
        else:
            asyncio.run(coro)
        return "Linterna del movil encendida." if state else "Linterna del movil apagada."

    if action in ("silent", "silencio", "dnd", "nomolestar"):
        silent_state = value.lower().strip() not in ("off", "desactivar", "false", "0", "sonar")
        coro = phone_manager.set_silent(silent_state)
        if loop and loop.is_running():
            asyncio.create_task(coro)
        else:
            asyncio.run(coro)
        return (
            "Modo silencio activado en el telefono."
            if silent_state
            else "Modo silencio desactivado en el telefono."
        )

    if action in ("send_file", "sendfile", "enviar_archivo", "enviararchivo", "archivo"):
        target_file = _resolve_file_for_phone(value)
        if not target_file:
            return f"No encontre el archivo '{value}' para enviar."
        try:
            rel_path = str(target_file.relative_to(Path.home()))
        except ValueError:
            rel_path = str(target_file)
        coro = phone_manager.push_file_to_phone(
            filename=target_file.name,
            remote_path=rel_path,
            size_bytes=target_file.stat().st_size,
        )
        if loop and loop.is_running():
            asyncio.create_task(coro)
        else:
            asyncio.run(coro)
        return f"Enviando '{target_file.name}' a tu telefono."

    if action in ("status", "estado", "bateria"):
        devices = phone_manager.list_connected_devices()
        if len(devices) > 1:
            res = []
            for d in devices:
                did = d.get("device_id", "Dispositivo")
                model = d.get("model", "")
                name = f"{did} ({model})" if model else did
                batt = d.get("battery")
                if batt is not None:
                    chg = "cargando" if d.get("is_charging") else "sin cargar"
                    res.append(f"{name}: {batt}% ({chg})")
                else:
                    res.append(f"{name}: bateria no reportada")
            return "Estado de tus dispositivos conectados: " + "; ".join(res) + "."

        info = phone_manager.get_device_status()
        batt = info.get("battery")
        if batt is not None:
            charging = "conectado al cargador" if info.get("is_charging") else "no esta cargando"
            device_name = info.get("device_id")
            prefix = f"A {device_name}" if device_name else "Al telefono"
            return f"{prefix} le queda un {batt}% de bateria y {charging}."
        return "El telefono esta vinculado pero aun no ha reportado nivel de bateria."

    if action in ("clipboard", "portapapeles", "copiar"):
        if not value:
            return "No se especifico ningun texto para enviar al telefono."
        coro = phone_manager.send_clipboard(value)
        if loop and loop.is_running():
            asyncio.create_task(coro)
        else:
            asyncio.run(coro)
        return "Texto copiado al portapapeles de tu movil."

    if action in ("open_url", "url", "enlace", "link"):
        if not value:
            return "No se especifico ninguna URL para enviar al telefono."
        coro = phone_manager.send_url(value)
        if loop and loop.is_running():
            asyncio.create_task(coro)
        else:
            asyncio.run(coro)
        return "Enlace enviado a tu movil."

    return f"Accion telefonica '{action}' no reconocida."


def _execute_via_http(action: str, value: str) -> str:
    """Ejecucion comunicandose con el servidor Bridge local via HTTP."""
    base_url = f"http://127.0.0.1:{BRIDGE_PORT}"
    headers = {"X-Bridge-Key": BRIDGE_API_KEY}

    try:
        with httpx.Client(base_url=base_url, headers=headers, timeout=2.0) as client:
            if action in ("ring", "sonar", "alarma"):
                resp = client.post("/api/v1/phone/ring", json={"duration_seconds": 15})
                if resp.status_code == 200:
                    return "Haciendo sonar tu telefono."
                return "No hay ningun telefono conectado al bridge actualmente."

            if action in ("status", "estado", "bateria"):
                dev_resp = client.get("/api/v1/phone/devices")
                if dev_resp.status_code == 200:
                    devices = dev_resp.json().get("devices", [])
                    if len(devices) > 1:
                        res = []
                        for d in devices:
                            did = d.get("device_id", "Dispositivo")
                            model = d.get("model", "")
                            name = f"{did} ({model})" if model else did
                            batt = d.get("battery")
                            if batt is not None:
                                chg = "cargando" if d.get("is_charging") else "sin cargar"
                                res.append(f"{name}: {batt}% ({chg})")
                            else:
                                res.append(f"{name}: sin datos de bateria")
                        return "Estado de tus dispositivos: " + "; ".join(res) + "."

                resp = client.get("/api/v1/phone/status")
                if resp.status_code == 200:
                    data: dict[str, Any] = resp.json()
                    batt = data.get("battery")
                    if batt is not None:
                        is_ch = data.get("is_charging")
                        charging = "conectado al cargador" if is_ch else "no esta cargando"
                        did = data.get("device_id")
                        prefix = f"A {did}" if did else "Al movil"
                        return f"{prefix} le queda un {batt}% de bateria y {charging}."
                    return (
                        "El telefono esta conectado pero no ha reportado su porcentaje de bateria."
                    )
                return "No hay ningun telefono conectado al bridge."

            if action in ("clipboard", "portapapeles", "copiar"):
                if not value:
                    return "No indicaste ningun texto para el portapapeles."
                resp = client.post("/api/v1/phone/clipboard", json={"text": value})
                if resp.status_code == 200:
                    return "Copiado al portapapeles de tu telefono."
                return "No se pudo enviar al telefono; comprueba la conexion."

            if action in ("open_url", "url", "enlace", "link"):
                if not value:
                    return "No indicaste ninguna URL para enviar."
                resp = client.post("/api/v1/phone/url", json={"url": value})
                if resp.status_code == 200:
                    return "Enlace abierto en tu telefono."
                return "No se pudo enviar el enlace al telefono."

            if action in ("send_file", "sendfile", "enviar_archivo", "enviararchivo", "archivo"):
                target_file = _resolve_file_for_phone(value)
                if not target_file:
                    return f"No encontre el archivo '{value}' para enviar."
                try:
                    rel_path = str(target_file.relative_to(Path.home()))
                except ValueError:
                    rel_path = str(target_file)
                resp = client.post(
                    "/api/v1/phone/send_file",
                    json={
                        "filename": target_file.name,
                        "remote_path": rel_path,
                        "size_bytes": target_file.stat().st_size,
                    },
                )
                if resp.status_code == 200:
                    return f"Enviando '{target_file.name}' a tu telefono."
                return "No se pudo enviar el archivo al telefono."

    except Exception as e:
        logger.debug("Servidor Bridge local no disponible en %s: %s", base_url, e)

    return "El servicio Jota Bridge no esta activo o no hay ningun telefono vinculado."


def capture_workspace_screenshot(workspace: int | None = None) -> Path | None:
    """
    Captura una imagen del escritorio completo o de un workspace especifico de Hyprland.
    Retorna la ruta al archivo PNG generado en BRIDGE_TEMP_DIR.
    """
    grim = shutil.which("grim")
    if not grim:
        logger.error("grim no esta disponible para capturar pantalla.")
        return None

    BRIDGE_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    ws_label = f"espacio_{workspace}" if workspace else "pantalla"
    out_file = BRIDGE_TEMP_DIR / f"captura_{ws_label}_{stamp}.png"

    hyprctl = shutil.which("hyprctl")
    if not hyprctl or workspace is None:
        try:
            res = subprocess.run(
                [grim, str(out_file)],
                capture_output=True,
                timeout=3,
                check=False,
            )
            if res.returncode == 0 and out_file.exists():
                return out_file
        except Exception as e:
            logger.error("Error al capturar pantalla con grim: %s", e)
        return None

    try:
        # Obtener workspace activo actual
        ws_proc = subprocess.run(
            [hyprctl, "activeworkspace", "-j"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        cur_ws = 1
        if ws_proc.returncode == 0 and ws_proc.stdout.strip():
            cur_ws = json.loads(ws_proc.stdout).get("id", 1)

        # Si el espacio solicitado ya esta activo en el monitor enfocado
        if cur_ws == workspace:
            res = subprocess.run(
                [grim, str(out_file)],
                capture_output=True,
                timeout=3,
                check=False,
            )
            if res.returncode == 0 and out_file.exists():
                return out_file
            return None

        # Comprobar si esta activo en algun otro monitor
        mon_proc = subprocess.run(
            [hyprctl, "monitors", "-j"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if mon_proc.returncode == 0 and mon_proc.stdout.strip():
            monitors = json.loads(mon_proc.stdout)
            for m in monitors:
                if m.get("activeWorkspace", {}).get("id") == workspace:
                    m_name = m.get("name")
                    res = subprocess.run(
                        [grim, "-o", m_name, str(out_file)],
                        capture_output=True,
                        timeout=3,
                        check=False,
                    )
                    if res.returncode == 0 and out_file.exists():
                        return out_file

        # Si no esta visible en ningun monitor, cambiar momentaneamente
        subprocess.run(
            [hyprctl, "dispatch", "workspace", str(workspace)],
            timeout=2,
            check=False,
        )
        time.sleep(0.15)
        res = subprocess.run(
            [grim, str(out_file)],
            capture_output=True,
            timeout=3,
            check=False,
        )

        # Restaurar workspace original
        subprocess.run(
            [hyprctl, "dispatch", "workspace", str(cur_ws)],
            timeout=2,
            check=False,
        )

        if res.returncode == 0 and out_file.exists():
            return out_file
    except Exception as e:
        logger.error("Error al capturar workspace %s: %s", workspace, e)

    return None


def send_screenshot_to_phone(workspace: int | None = None) -> tuple[bool, str]:
    """Captura el workspace o la pantalla y la envia al telefono."""
    shot_path = capture_workspace_screenshot(workspace)
    if not shot_path or not shot_path.exists():
        return False, "No se pudo tomar la captura de pantalla."

    msg = phone_control("send_file", str(shot_path))
    if "No" in msg and "encontre" in msg:
        return False, msg

    ws_text = f"del espacio {workspace}" if workspace else "de la pantalla"
    return True, f"Captura {ws_text} enviada a tu telefono."


def get_active_browser_url() -> str | None:
    """Detecta la URL activa del navegador o copiada en el portapapeles."""
    # 1. Verificar portapapeles
    wl_paste = shutil.which("wl-paste")
    if wl_paste:
        try:
            res = subprocess.run(
                [wl_paste],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            if res.returncode == 0:
                text_val = res.stdout.strip()
                if text_val.startswith("http://") or text_val.startswith("https://"):
                    return text_val
        except Exception:
            pass

    # 2. Consultar historial reciente de Firefox (places.sqlite)
    ff_dir = Path.home() / ".mozilla" / "firefox"
    if ff_dir.exists():
        profiles = list(ff_dir.glob("*.default-release")) or list(ff_dir.glob("*.default*"))
        for prof in profiles:
            db_path = prof / "places.sqlite"
            if db_path.exists():
                tmp_db = Path("/tmp") / f"places_tmp_{prof.name}.sqlite"
                try:
                    shutil.copy2(db_path, tmp_db)
                    con = sqlite3.connect(tmp_db)
                    cur = con.cursor()
                    cur.execute(
                        """
                        SELECT url FROM moz_places
                        JOIN moz_historyvisits ON moz_places.id = moz_historyvisits.place_id
                        ORDER BY visit_date DESC LIMIT 1
                        """
                    )
                    row = cur.fetchone()
                    con.close()
                    tmp_db.unlink(missing_ok=True)
                    if row and row[0]:
                        return row[0]
                except Exception as e:
                    logger.debug("Error consultando places.sqlite: %s", e)

    return None


def send_active_url_to_phone(url: str = "") -> tuple[bool, str]:
    """Envia una URL al navegador del telefono."""
    target_url = str(url).strip()
    is_valid_http = target_url.startswith("http://") or target_url.startswith("https://")
    if not target_url or not is_valid_http:
        target_url = get_active_browser_url() or ""

    if not target_url:
        return False, "No encontre ninguna URL activa ni en el portapapeles para enviar."

    msg = phone_control("open_url", target_url)
    return True, msg


def get_selected_or_active_file() -> Path | None:
    """Localiza el archivo seleccionado en el explorador o el mas reciente."""
    # 1. Comprobar si hay URIs en el portapapeles o seleccion primaria (Dolphin / KDE)
    wl_paste = shutil.which("wl-paste")
    if wl_paste:
        for extra_args in [[], ["--primary"]]:
            try:
                res = subprocess.run(
                    [wl_paste, *extra_args, "-t", "text/uri-list"],
                    capture_output=True,
                    text=True,
                    timeout=1,
                    check=False,
                )
                if res.returncode == 0 and res.stdout.strip():
                    for line in res.stdout.strip().splitlines():
                        if line.startswith("file://"):
                            p = Path(unquote(urlparse(line.strip()).path))
                            if p.is_file():
                                return p
            except Exception:
                pass

            # Comprobar texto plano en clipboard o seleccion primaria
            try:
                res_txt = subprocess.run(
                    [wl_paste, *extra_args],
                    capture_output=True,
                    text=True,
                    timeout=1,
                    check=False,
                )
                if res_txt.returncode == 0:
                    candidate = Path(res_txt.stdout.strip()).expanduser()
                    if candidate.is_file():
                        return candidate
            except Exception:
                pass

    # 2. Archivo reciente en Descargas o Documentos (ultimos 15 min)
    now = time.time()
    search_dirs = [
        Path.home() / "Descargas",
        Path.home() / "Downloads",
        Path.home() / "Documentos",
    ]
    for folder in search_dirs:
        if folder.exists():
            files = [f for f in folder.iterdir() if f.is_file()]
            if files:
                files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                latest = files[0]
                if now - latest.stat().st_mtime < 900:  # 15 minutos
                    return latest

    return None


def send_active_file_to_phone(target: str = "") -> tuple[bool, str]:
    """Envia un archivo especifico o seleccionado al movil."""
    clean_target = str(target).strip()
    is_generic = not clean_target or clean_target.lower() in (
        "este",
        "este archivo",
        "el archivo",
        "seleccionado",
        "el archivo seleccionado",
        "este documento",
        "documento",
    )

    if is_generic:
        file_path = get_selected_or_active_file()
    else:
        file_path = _resolve_file_for_phone(clean_target)

    if not file_path or not file_path.is_file():
        return False, "No encontre ningun archivo seleccionado ni reciente para enviar."

    msg = phone_control("send_file", str(file_path))
    return True, msg


def main() -> None:
    """Punto de entrada de consola para enviar archivos seleccionados al movil."""
    import sys

    files = sys.argv[1:]
    if not files:
        ok, msg = send_active_file_to_phone()
        print(msg)
        if shutil.which("notify-send"):
            subprocess.run(["notify-send", "Jota Bridge", msg], check=False)
        return

    for f in files:
        p = Path(f).resolve()
        if p.is_file():
            ok, msg = send_active_file_to_phone(str(p))
            print(msg)
            if shutil.which("notify-send"):
                subprocess.run(["notify-send", "Jota Bridge", msg], check=False)


if __name__ == "__main__":
    main()



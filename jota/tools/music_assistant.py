"""
Integracion con Music Assistant (2.x) mediante API WebSocket para reproduccion,
control y transferencia fluida (handoff) de musica entre el PC y el telefono movil.
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import websockets

from jota.config import (
    MUSIC_ASSISTANT_CONFIG,
    MUSIC_ASSISTANT_TOKEN,
    MUSIC_ASSISTANT_URL,
)

logger = logging.getLogger(__name__)

_working_ws_url: str | None = None


def _load_auth_token() -> str:
    """Carga el token de autenticacion de Music Assistant desde configuracion o entorno."""
    if MUSIC_ASSISTANT_TOKEN:
        return MUSIC_ASSISTANT_TOKEN.strip()

    cfg_file = Path(MUSIC_ASSISTANT_CONFIG)
    if cfg_file.is_file():
        try:
            with open(cfg_file, encoding="utf-8") as fp:
                data = json.load(fp)
                token = data.get("token") or data.get("api_key") or ""
                if token:
                    return str(token).strip()
        except Exception as e:
            logger.debug("Error leyendo config de Music Assistant: %s", e)

    return ""


def _get_ws_candidates() -> list[str]:
    """Retorna la lista de URLs WebSocket candidatas para conectar con Music Assistant."""
    urls: list[str] = []
    if _working_ws_url:
        urls.append(_working_ws_url)

    if MUSIC_ASSISTANT_URL:
        parsed = urlparse(MUSIC_ASSISTANT_URL)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        netloc = parsed.netloc or f"{parsed.hostname}:{parsed.port or 8095}"
        ws = f"{scheme}://{netloc}/ws"
        if ws not in urls:
            urls.append(ws)

    # Candidatos adicionales configurados por entorno o mass.json
    extra_fallback = os.getenv("MUSIC_ASSISTANT_FALLBACK_URL", "")
    if extra_fallback:
        parsed_ex = urlparse(extra_fallback)
        scheme_ex = "wss" if parsed_ex.scheme == "https" else "ws"
        netloc_ex = parsed_ex.netloc or f"{parsed_ex.hostname}:{parsed_ex.port or 8095}"
        ws_ex = f"{scheme_ex}://{netloc_ex}/ws"
        if ws_ex not in urls:
            urls.append(ws_ex)

    return urls


async def _send_mass_command(
    command: str,
    args: dict[str, Any] | None = None,
    timeout: float = 3.5,
) -> tuple[bool, Any]:
    """
    Se conecta al WebSocket de Music Assistant, autentica si es necesario
    y ejecuta el comando solicitado. Devuelve (exito, datos_o_error).
    Prueba URLs alternativas con conmutacion por error automatica.
    """
    global _working_ws_url
    token = _load_auth_token()
    last_err: str = "No se pudo conectar a Music Assistant"

    candidates = _get_ws_candidates()
    for ws_url in candidates:
        try:
            async with websockets.connect(
                ws_url,
                open_timeout=2.0,
                close_timeout=1.5,
            ) as ws:
                # 1. Handshake inicial del servidor
                init_raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                init_data = json.loads(init_raw)
                logger.debug(
                    "Music Assistant handshake exitoso en %s (%s)",
                    ws_url,
                    init_data.get("name"),
                )

                # 2. Autenticacion si hay token configurado
                msg_id = 1
                if token:
                    auth_cmd = {
                        "message_id": msg_id,
                        "command": "auth",
                        "args": {"token": token},
                    }
                    await ws.send(json.dumps(auth_cmd))
                    auth_resp_raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    auth_resp = json.loads(auth_resp_raw)
                    if auth_resp.get("error_code"):
                        logger.warning(
                            "Fallo auth en Music Assistant: %s",
                            auth_resp.get("details"),
                        )
                        return False, f"Error de autenticacion: {auth_resp.get('details')}"
                    msg_id += 1

                # 3. Enviar comando principal
                cmd_payload: dict[str, Any] = {"message_id": msg_id, "command": command}
                if args:
                    cmd_payload["args"] = args

                await ws.send(json.dumps(cmd_payload))

                # Esperar respuesta correspondiente filtrando eventos de difusion
                while True:
                    resp_raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    resp = json.loads(resp_raw)
                    m_id = resp.get("message_id")
                    if m_id is not None and (m_id == msg_id or str(m_id) == str(msg_id)):
                        _working_ws_url = ws_url
                        if resp.get("error_code"):
                            err_msg = resp.get("details") or "Error en Music Assistant"
                            return False, err_msg
                        return True, resp.get("result")

        except Exception as e:
            last_err = str(e)
            logger.debug("Intento fallido con Music Assistant en %s: %s", ws_url, e)

    return False, last_err


def get_players() -> list[dict[str, Any]]:
    """Consulta la lista de reproductores registrados en Music Assistant."""
    try:
        success, result = asyncio.run(_send_mass_command("players/all"))
        if success and isinstance(result, list):
            return result
    except Exception as e:
        logger.debug("Error listando reproductores de Music Assistant: %s", e)
    return []


def get_queues() -> list[dict[str, Any]]:
    """Consulta todas las colas de reproduccion registradas en Music Assistant."""
    try:
        success, result = asyncio.run(_send_mass_command("player_queues/all"))
        if success and isinstance(result, list):
            return result
    except Exception as e:
        logger.debug("Error listando colas de Music Assistant: %s", e)
    return []


def wake_mobile_player(timeout_sec: float = 2.0) -> bool:
    """
    Despierta la app de Music Assistant en el telefono si esta suspendida o desconectada.
    Usa ADB para iniciar la actividad principal y espera a que aparezca registrada.
    """
    # 1. Comprobar si ya esta disponible
    for p in get_players():
        if p.get("available") and any(
            k in p.get("name", "").lower() for k in ("xiaomi", "movil", "móvil", "phone")
        ):
            return True

    # 2. Despertar cliente via ADB si hay dispositivo conectado
    if shutil.which("adb"):
        try:
            res = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
            if any(line.endswith("\tdevice") for line in res.stdout.splitlines()):
                subprocess.run(
                    [
                        "adb",
                        "shell",
                        "am",
                        "start",
                        "-n",
                        "io.music_assistant.client/.MainActivity",
                    ],
                    capture_output=True,
                    timeout=2.0,
                    check=False,
                )
                logger.info("Comando de reactivacion enviado a io.music_assistant.client via ADB.")
        except Exception as e:
            logger.debug("Error intentando despertar app en movil via ADB: %s", e)

    # 3. Esperar confirmacion de registro en Music Assistant
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        time.sleep(0.2)
        for p in get_players():
            if p.get("available") and any(
                k in p.get("name", "").lower() for k in ("xiaomi", "movil", "móvil", "phone")
            ):
                logger.info("Reproductor movil detectado y disponible: %s", p.get("name"))
                return True

    return False


def _score_player(p: dict[str, Any], target_alias: str) -> int:
    """Calcula una puntuacion de coincidencia para seleccionar el reproductor adecuado."""
    target = target_alias.lower().strip()
    p_name = p.get("name", "").lower()
    p_type = p.get("type", "").lower()
    score = 0

    if p.get("available"):
        score += 100
    else:
        score -= 50

    is_phone_target = any(
        k in target for k in ("movil", "móvil", "telefono", "teléfono", "celular", "phone")
    )
    is_pc_target = any(
        k in target for k in ("pc", "ordenador", "escritorio", "computadora", "linux", "desktop")
    )
    is_tv_target = any(k in target for k in ("tele", "televisión", "television", "tv", "salon"))

    phone_k = ("xiaomi", "movil", "móvil", "phone", "android")
    pc_k = ("pwa", "chrome", "linux", "web", "pc", "escritorio", "desktop")
    tv_k = ("50pus", "philips", "tv", "tele")

    if is_phone_target:
        if any(k in p_name for k in phone_k) or "mobile" in p_type:
            score += 150
        elif any(k in p_name for k in pc_k) or any(k in p_name for k in tv_k):
            score -= 300
    elif is_pc_target:
        if any(k in p_name for k in pc_k):
            score += 150
        elif "monitor" in p_name:
            score += 10
        elif any(k in p_name for k in phone_k) or any(k in p_name for k in tv_k):
            score -= 300
    elif is_tv_target:
        if any(k in p_name for k in tv_k):
            score += 150
        elif any(k in p_name for k in phone_k) or any(k in p_name for k in pc_k):
            score -= 300

    if p.get("state") == "playing":
        score += 20
    elif p.get("state") == "paused":
        score += 10

    return score


def _score_queue(q: dict[str, Any], target_alias: str) -> int:
    """Calcula una puntuacion de coincidencia para seleccionar la cola adecuada."""
    target = target_alias.lower().strip()
    q_name = q.get("display_name", "").lower()
    score = 0

    if q.get("available"):
        score += 100
    else:
        score -= 100

    if q.get("state") == "playing":
        score += 30
    elif q.get("state") == "paused":
        score += 10

    if (q.get("items") or 0) > 0:
        score += 20
    if q.get("current_item") is not None:
        score += 10

    is_phone_target = any(
        k in target for k in ("movil", "móvil", "telefono", "teléfono", "celular", "phone")
    )
    is_pc_target = any(
        k in target for k in ("pc", "ordenador", "escritorio", "computadora", "linux", "desktop")
    )
    is_tv_target = any(k in target for k in ("tele", "televisión", "television", "tv", "salon"))

    phone_k = ("xiaomi", "movil", "móvil", "phone", "android")
    pc_k = ("pwa", "chrome", "linux", "web", "pc", "escritorio", "desktop")
    tv_k = ("50pus", "philips", "tv", "tele")

    if is_phone_target:
        if any(k in q_name for k in phone_k):
            score += 150
        elif any(k in q_name for k in pc_k) or any(k in q_name for k in tv_k):
            score -= 300
    elif is_pc_target:
        if any(k in q_name for k in pc_k):
            score += 150
        elif "monitor" in q_name:
            score += 10
        elif any(k in q_name for k in phone_k) or any(k in q_name for k in tv_k):
            score -= 300
    elif is_tv_target:
        if any(k in q_name for k in tv_k):
            score += 150
        elif any(k in q_name for k in phone_k) or any(k in q_name for k in pc_k):
            score -= 300

    return score


def _resolve_queue_id(target_alias: str, queues: list[dict[str, Any]]) -> str | None:
    """Resuelve un alias a la cola de reproduccion mas idonea priorizando dispositivos activos."""
    if not queues:
        return None
    scored = [(q, _score_queue(q, target_alias)) for q in queues]
    scored.sort(key=lambda item: item[1], reverse=True)
    best_q, best_score = scored[0]
    if best_score > 0:
        return best_q.get("queue_id")
    return None


def _resolve_player_id(target_alias: str, players: list[dict[str, Any]]) -> str | None:
    """Resuelve un alias al ID del reproductor correspondiente con orden de prioridad."""
    if not players:
        return None
    scored = [(p, _score_player(p, target_alias)) for p in players]
    scored.sort(key=lambda item: item[1], reverse=True)
    best_p, best_score = scored[0]
    if best_score > 0:
        return best_p.get("player_id")
    return None


def transfer_music(source_alias: str = "pc", target_alias: str = "movil") -> tuple[bool, str]:
    """
    Transfiere la reproduccion de musica de Music Assistant entre dos dispositivos.
    Ejemplo: de PC al movil o viceversa.
    Soporta handoff desde colas de Music Assistant o desde reproductores MPRIS (playerctl).
    """
    token = _load_auth_token()
    if not token:
        hint = (
            "Music Assistant configurado en elitedesk. Configura tu token en "
            "~/.config/jota/mass.json para autorizar el control."
        )
        logger.info(hint)
        from jota.tools.navidrome import transfer_playback_to_phone

        fb_ok, fb_msg = transfer_playback_to_phone()
        if fb_ok:
            return True, f"Musica transferida a tu movil via Navidrome ({fb_msg})."
        return False, hint

    # Si el destino es el movil, asegurar que la aplicacion este activa
    phone_keywords = ("movil", "móvil", "telefono", "teléfono", "celular")
    if any(k in target_alias.lower() for k in phone_keywords):
        wake_mobile_player(timeout_sec=1.5)

    queues = get_queues()
    players = get_players()
    if not queues and not players:
        from jota.tools.navidrome import transfer_playback_to_phone

        fb_ok, fb_msg = transfer_playback_to_phone()
        if fb_ok:
            return True, f"Musica transferida a tu movil via Navidrome ({fb_msg})."
        return False, "No se encontraron reproductores disponibles en Music Assistant."

    target_id = _resolve_queue_id(target_alias, queues) or _resolve_player_id(target_alias, players)
    if not target_id:
        if any(k in target_alias.lower() for k in phone_keywords):
            from jota.tools.navidrome import transfer_playback_to_phone

            fb_ok, fb_msg = transfer_playback_to_phone()
            if fb_ok:
                return True, f"Musica transferida a tu movil via Navidrome ({fb_msg})."
        return False, f"No se encontro el reproductor destino '{target_alias}' en Music Assistant."

    # 1. Encontrar la cola de origen que realmente tenga canciones o reproduccion activa
    source_id = None

    # Prioridad A: Cola en estado playing distinta a la destino con disponibilidad
    for q in queues:
        if (
            q.get("state") == "playing"
            and q.get("available")
            and q.get("queue_id") != target_id
            and ((q.get("items") or 0) > 0 or q.get("current_item") is not None)
        ):
            source_id = q.get("queue_id")
            break

    # Prioridad B: Cola en estado paused con canciones
    if not source_id:
        for q in queues:
            if (
                q.get("state") == "paused"
                and q.get("available")
                and (q.get("items") or 0) > 0
                and q.get("queue_id") != target_id
            ):
                source_id = q.get("queue_id")
                break

    # Prioridad C: Cola que coincida con source_alias con canciones
    if not source_id:
        for q in queues:
            if (
                q.get("available")
                and (q.get("items") or 0) > 0
                and q.get("queue_id") != target_id
                and _score_queue(q, source_alias) > 50
            ):
                source_id = q.get("queue_id")
                break

    # Prioridad D: Cualquier cola disponible con canciones distinta de destino
    if not source_id:
        for q in queues:
            if (
                q.get("available")
                and (q.get("items") or 0) > 0
                and q.get("queue_id") != target_id
            ):
                source_id = q.get("queue_id")
                break

    # Si la cola elegida como origen es la misma que el destino, asegurar reproduccion
    if source_id == target_id:
        asyncio.run(_send_mass_command("player_queues/play", args={"queue_id": target_id}))
        return True, f"La musica ya se encuentra asignada a {target_alias}."

    # Si habia cola activa con pistas en Music Assistant, transferir la cola
    if source_id:
        success, res = asyncio.run(
            _send_mass_command(
                "player_queues/transfer",
                args={
                    "source_queue_id": source_id,
                    "target_queue_id": target_id,
                    "auto_play": True,
                },
            )
        )
        if success:
            time.sleep(0.3)
            # Verificar si arranco o requiere play explicito
            t_queues = get_queues()
            target_q = next((q for q in t_queues if q.get("queue_id") == target_id), None)
            if target_q and target_q.get("state") != "playing":
                asyncio.run(_send_mass_command("player_queues/play", args={"queue_id": target_id}))
            return True, f"Musica transferida a {target_alias} en Music Assistant."
        logger.warning("Fallo transferencia directa de cola: %s", res)

    # Si la musica ya se encuentra en la cola destino y ninguna otra tiene pistas, reanudar
    target_q = next((q for q in queues if q.get("queue_id") == target_id), None)
    if not source_id and target_q and (target_q.get("items") or 0) > 0:
        asyncio.run(_send_mass_command("player_queues/play", args={"queue_id": target_id}))
        return True, f"Reanudando reproduccion de musica en {target_alias} en Music Assistant."

    # 2. Si Music Assistant no tenia canciones en cola, comprobar reproductor local (playerctl)
    if shutil.which("playerctl"):
        stat_p = subprocess.run(
            ["playerctl", "status"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
        if "Playing" in stat_p.stdout:
            proc_m = subprocess.run(
                ["playerctl", "metadata", "--format", "{{title}}\t{{artist}}"],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
            if proc_m.returncode == 0 and proc_m.stdout.strip():
                track_parts = [p.strip() for p in proc_m.stdout.strip().split("\t") if p.strip()]
                title = track_parts[0] if track_parts else ""
                artist = track_parts[1] if len(track_parts) > 1 else ""

                # Filtrar pestañas de video generales que no sean pistas de musica
                is_video = any(
                    k in title.lower() for k in ("prime video", "netflix", "twitch")
                )
                if (artist or not is_video) and title:
                    query = f"{artist} {title}".strip() if artist else title
                    subprocess.run(["playerctl", "pause"], capture_output=True, check=False)
                    ok_play, msg_play = play_music_assistant(query, target_alias=target_alias)
                    if ok_play:
                        msg = f"Musica ({query}) transferida a {target_alias} en Music Assistant."
                        return True, msg

    # 3. Fallback transparente con Navidrome
    if any(k in target_alias.lower() for k in phone_keywords):
        logger.info("Transfiriendo reproduccion via Navidrome...")
        from jota.tools.navidrome import transfer_playback_to_phone

        fb_ok, fb_msg = transfer_playback_to_phone()
        if fb_ok:
            return True, f"Musica transferida a tu movil via Navidrome ({fb_msg})."

    return False, "No hay ninguna musica reproduciendose actualmente para transferir."


def play_music_assistant(query: str, target_alias: str = "pc") -> tuple[bool, str]:
    """Inicia la reproduccion de un artista, cancion o radio en Music Assistant."""
    token = _load_auth_token()
    if not token:
        from jota.tools.navidrome import play_navidrome_smart_radio

        return play_navidrome_smart_radio(query)

    phone_keywords = ("movil", "móvil", "telefono", "teléfono", "celular")
    if any(k in target_alias.lower() for k in phone_keywords):
        wake_mobile_player(timeout_sec=1.5)

    players = get_players()
    queues = get_queues()
    target_id = _resolve_queue_id(target_alias, queues) or _resolve_player_id(target_alias, players)
    if not target_id and players:
        target_id = players[0].get("player_id")

    if not target_id:
        from jota.tools.navidrome import play_navidrome_smart_radio

        return play_navidrome_smart_radio(query)

    # Buscar item especifico en el catalogo
    media_item: str = query
    success, s_res = asyncio.run(
        _send_mass_command("music/search", args={"search_query": query, "limit": 1})
    )
    if success and isinstance(s_res, dict):
        tracks = s_res.get("tracks") or []
        artists = s_res.get("artists") or []
        albums = s_res.get("albums") or []
        if tracks:
            media_item = tracks[0].get("uri") or query
        elif artists:
            media_item = artists[0].get("uri") or query
        elif albums:
            media_item = albums[0].get("uri") or query

    args = {"queue_id": target_id, "media": media_item}
    success, res = asyncio.run(_send_mass_command("player_queues/play_media", args=args))
    if success:
        time.sleep(0.2)
        asyncio.run(_send_mass_command("player_queues/play", args={"queue_id": target_id}))
        return True, f"Reproduciendo '{query}' en {target_alias} via Music Assistant."

    # Fallback con Navidrome
    from jota.tools.navidrome import play_navidrome_smart_radio

    return play_navidrome_smart_radio(query)


def media_control_mass(action: str, target_alias: str = "") -> tuple[bool, str]:
    """Controla pausa, reanudacion o pista siguiente en Music Assistant."""
    cmd_map = {
        "pause": "player_queues/pause",
        "play": "player_queues/play",
        "resume": "player_queues/resume",
        "next": "player_queues/next",
        "previous": "player_queues/previous",
    }
    cmd = cmd_map.get(action.lower().strip())
    if not cmd:
        return False, f"Accion no soportada: {action}"

    players = get_players()
    queues = get_queues()
    target_id = (
        _resolve_queue_id(target_alias, queues) or _resolve_player_id(target_alias, players)
        if target_alias
        else None
    )

    if not target_id and queues:
        for q in queues:
            if q.get("state") == "playing" and q.get("available"):
                target_id = q.get("queue_id")
                break
        if not target_id:
            for q in queues:
                if q.get("available"):
                    target_id = q.get("queue_id")
                    break

    args = {"queue_id": target_id} if target_id else None
    success, res = asyncio.run(_send_mass_command(cmd, args=args))
    if success:
        return True, f"Comando '{action}' enviado a Music Assistant."
    return False, f"Error en comando Music Assistant: {res}"

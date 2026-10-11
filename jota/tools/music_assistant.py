"""
Integracion con Music Assistant (2.x) mediante API WebSocket para reproduccion,
control y transferencia fluida (handoff) de musica entre el PC y el telefono movil.
"""

import asyncio
import json
import logging
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


def _get_ws_url() -> str:
    """Transforma la URL HTTP en URL WebSocket para Music Assistant."""
    parsed = urlparse(MUSIC_ASSISTANT_URL)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc or f"{parsed.hostname}:{parsed.port or 8095}"
    return f"{scheme}://{netloc}/ws"


async def _send_mass_command(
    command: str,
    args: dict[str, Any] | None = None,
    timeout: float = 4.0,
) -> tuple[bool, Any]:
    """
    Se conecta al WebSocket de Music Assistant, autentica si es necesario
    y ejecuta el comando solicitado. Devuelve (exito, datos_o_error).
    """
    ws_url = _get_ws_url()
    token = _load_auth_token()

    try:
        async with websockets.connect(ws_url, close_timeout=2.0) as ws:
            # 1. Handshake inicial del servidor
            init_raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            init_data = json.loads(init_raw)
            logger.debug("Music Assistant handshake: %s", init_data.get("name"))

            # 2. Autenticacion si hay token configurado
            msg_id = 1
            if token:
                auth_cmd = {"message_id": msg_id, "command": "auth", "args": {"token": token}}
                await ws.send(json.dumps(auth_cmd))
                auth_resp_raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                auth_resp = json.loads(auth_resp_raw)
                if auth_resp.get("error_code"):
                    logger.warning("Fallo auth en Music Assistant: %s", auth_resp.get("details"))
                    return False, f"Error de autenticacion: {auth_resp.get('details')}"
                msg_id += 1

            # 3. Enviar comando principal
            cmd_payload = {"message_id": msg_id, "command": command}
            if args:
                cmd_payload["args"] = args

            await ws.send(json.dumps(cmd_payload))

            # Esperar respuesta correspondiente filtrando eventos de difusion
            while True:
                resp_raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                resp = json.loads(resp_raw)
                m_id = resp.get("message_id")
                if m_id is not None and (m_id == msg_id or str(m_id) == str(msg_id)):
                    if resp.get("error_code"):
                        err_msg = resp.get("details") or "Error en Music Assistant"
                        return False, err_msg
                    return True, resp.get("result")

    except TimeoutError:
        return False, "Tiempo de espera agotado al conectar con Music Assistant"
    except Exception as e:
        logger.debug("Error en comunicacion con Music Assistant: %s", e)
        return False, str(e)


def get_players() -> list[dict[str, Any]]:
    """Consulta la lista de reproductores registrados en Music Assistant."""
    try:
        success, result = asyncio.run(_send_mass_command("players/all"))
        if success and isinstance(result, list):
            return result
    except Exception as e:
        logger.debug("Error listando reproductores de Music Assistant: %s", e)
    return []


def _resolve_player_id(target_alias: str, players: list[dict[str, Any]]) -> str | None:
    """Resuelve un alias ('movil', 'pc', 'tele') al ID del reproductor correspondiente."""
    target_clean = target_alias.lower().strip()
    phone_keywords = ("movil", "móvil", "telefono", "teléfono", "xiaomi", "celular", "phone")
    pc_keywords = (
        "pc", "escritorio", "computadora", "ordenador", "fedora", "desktop",
        "chrome", "linux", "web", "monitor",
    )
    tv_keywords = (
        "tele", "televisión", "television", "tv", "salon", "salón", "chromecast",
        "50pus", "philips", "pus",
    )

    for p in players:
        p_name = p.get("name", "").lower()
        p_id = p.get("player_id", "")
        p_type = p.get("type", "").lower()

        if any(k in target_clean for k in phone_keywords):
            if any(k in p_name for k in phone_keywords) or "mobile" in p_type:
                return p_id

        if any(k in target_clean for k in pc_keywords):
            if any(k in p_name for k in (
                "pc", "escritorio", "computadora", "ordenador", "fedora",
                "desktop", "chrome", "linux", "web", "monitor",
            )):
                return p_id

        if any(k in target_clean for k in tv_keywords):
            if any(k in p_name for k in (
                "tele", "televisión", "television", "tv", "salon", "salón",
                "chromecast", "50pus", "philips", "pus",
            )):
                return p_id

    # Fallback por coincidencia parcial en nombre
    for p in players:
        if target_clean in p.get("name", "").lower():
            return p.get("player_id")

    return None


def transfer_music(source_alias: str = "pc", target_alias: str = "movil") -> tuple[bool, str]:
    """
    Transfiere la reproduccion de musica de Music Assistant entre dos dispositivos.
    Ejemplo: de PC al movil o viceversa.
    """
    token = _load_auth_token()
    if not token:
        hint = (
            "Music Assistant detectado en elitedesk. Configura tu token en "
            "~/.config/jota/mass.json para autorizar el control."
        )
        logger.info(hint)
        from jota.tools.navidrome import transfer_playback_to_phone
        fb_ok, fb_msg = transfer_playback_to_phone()
        if fb_ok:
            return True, f"Musica transferida a tu movil via Navidrome ({fb_msg})."
        return False, hint

    players = get_players()
    if not players:
        return False, "No se encontraron reproductores disponibles en Music Assistant."

    target_id = _resolve_player_id(target_alias, players)
    if not target_id:
        # Fallback a Navidrome si el destino es el movil
        phone_keywords = ("movil", "móvil", "telefono", "teléfono", "celular")
        if any(k in target_alias.lower() for k in phone_keywords):
            from jota.tools.navidrome import transfer_playback_to_phone
            fb_ok, fb_msg = transfer_playback_to_phone()
            if fb_ok:
                return True, f"Musica transferida a tu movil via Navidrome ({fb_msg})."
        return False, f"No se encontro el reproductor destino '{target_alias}' en Music Assistant."

    # Encontrar reproductor fuente activo
    source_id = _resolve_player_id(source_alias, players)
    if not source_id:
        for p in players:
            if p.get("state") == "playing":
                source_id = p.get("player_id")
                break

    if not source_id:
        source_id = players[0].get("player_id")

    if source_id == target_id:
        return True, "La musica ya se encuentra asignada al dispositivo seleccionado."

    success, res = asyncio.run(
        _send_mass_command(
            "player_queues/transfer",
            args={
                "source_queue_id": source_id,
                "target_queue_id": target_id,
            },
        )
    )

    if success:
        return True, f"Musica transferida a {target_alias} en Music Assistant."

    # Si Music Assistant falla por disponibilidad, fallback transparente a Navidrome
    phone_keywords = ("movil", "móvil", "telefono", "teléfono", "celular")
    if any(k in target_alias.lower() for k in phone_keywords):
        logger.info("Transferencia fallida en Music Assistant (%s); usando Navidrome.", res)
        from jota.tools.navidrome import transfer_playback_to_phone
        fb_ok, fb_msg = transfer_playback_to_phone()
        if fb_ok:
            return True, f"Musica transferida al movil ({fb_msg})."

    return False, f"No se pudo transferir en Music Assistant: {res}"


def play_music_assistant(query: str, target_alias: str = "pc") -> tuple[bool, str]:
    """Inicia la reproduccion de un artista, cancion o radio en Music Assistant."""
    token = _load_auth_token()
    if not token:
        from jota.tools.navidrome import play_navidrome_smart_radio
        return play_navidrome_smart_radio(query)

    players = get_players()
    target_id = _resolve_player_id(target_alias, players) if players else None
    if not target_id and players:
        target_id = players[0].get("player_id")

    if not target_id:
        from jota.tools.navidrome import play_navidrome_smart_radio
        return play_navidrome_smart_radio(query)

    # Intentar buscar item especifico (pista, artista, album)
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
    target_id = _resolve_player_id(target_alias, players) if (target_alias and players) else None
    if not target_id and players:
        for p in players:
            if p.get("state") == "playing":
                target_id = p.get("player_id")
                break
        if not target_id:
            target_id = players[0].get("player_id")

    args = {"queue_id": target_id} if target_id else None
    success, res = asyncio.run(_send_mass_command(cmd, args=args))
    if success:
        return True, f"Comando '{action}' enviado a Music Assistant."
    return False, f"Error en comando Music Assistant: {res}"

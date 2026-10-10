"""
Integracion con Navidrome (API Subsonic/OpenSubsonic) para generacion de colas
inteligentes tipo emisora de radio (Siri-style) y transferencia fluida (handoff) al movil.
"""

import json
import logging
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from typing import Any

from jota.config import (
    NAVIDROME_SALT,
    NAVIDROME_TOKEN,
    NAVIDROME_URL,
    NAVIDROME_USER,
)

logger = logging.getLogger(__name__)

# Estado en memoria de reproduccion interna de Jota
_active_proc: subprocess.Popen | None = None
_current_queue: list[dict[str, Any]] = []
_current_index: int = 0
_start_timestamp: float = 0.0
_paused_elapsed_seconds: float = 0.0
_is_paused: bool = False


def _get_subsonic_url(endpoint: str, extra_params: dict[str, Any] | None = None) -> str:
    """Construye la URL firmada para la API Subsonic."""
    params = {
        "u": NAVIDROME_USER,
        "s": NAVIDROME_SALT,
        "t": NAVIDROME_TOKEN,
        "v": "1.16.1",
        "c": "jota",
        "f": "json",
    }
    if extra_params:
        params.update(extra_params)
    query_str = urllib.parse.urlencode(params)
    return f"{NAVIDROME_URL.rstrip('/')}/rest/{endpoint}.view?{query_str}"


def _call_subsonic(
    endpoint: str,
    params: dict[str, Any] | None = None,
    timeout: float = 6.0,
) -> dict[str, Any]:
    """Realiza una peticion HTTP a la API Subsonic con cabecera de navegador valida."""
    url = _get_subsonic_url(endpoint, params)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Jota/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("subsonic-response", {})
    except Exception as e:
        logger.debug("Error en llamada Subsonic %s: %s", endpoint, e)
        return {}


def get_stream_url(song_id: str) -> str:
    """Genera la URL directa de streaming para un ID de cancion."""
    return _get_subsonic_url("stream", {"id": song_id})


def search_song(query: str) -> dict[str, Any] | None:
    """Busca una cancion por titulo o artista en Navidrome."""
    res = _call_subsonic("search3", {"query": query})
    songs = res.get("searchResult3", {}).get("song", [])
    if songs:
        return songs[0]
    return None


def build_smart_radio_queue(target_song: dict[str, Any], count: int = 15) -> list[dict[str, Any]]:
    """
    Construye una cola dinamica de reproduccion con canciones similares
    o del mismo genero y artista (Siri-style radio).
    """
    queue = [target_song]
    seen_ids = {target_song.get("id")}

    # 1. Intentar obtener canciones del mismo genero
    genre = target_song.get("genre")
    if genre:
        random_res = _call_subsonic("getRandomSongs", {"genre": genre, "size": count})
        songs = random_res.get("randomSongs", {}).get("song", [])
        for s in songs:
            sid = s.get("id")
            if sid and sid not in seen_ids:
                queue.append(s)
                seen_ids.add(sid)

    # 2. Si faltan canciones, buscar mas canciones del mismo artista
    artist_id = target_song.get("artistId")
    if len(queue) < count and artist_id:
        artist_res = _call_subsonic("getArtist", {"id": artist_id})
        albums = artist_res.get("artist", {}).get("album", [])
        for alb in albums:
            alb_id = alb.get("id")
            if alb_id:
                alb_res = _call_subsonic("getAlbum", {"id": alb_id})
                album_songs = alb_res.get("album", {}).get("song", [])
                for s in album_songs:
                    sid = s.get("id")
                    if sid and sid not in seen_ids:
                        queue.append(s)
                        seen_ids.add(sid)
                    if len(queue) >= count:
                        break
            if len(queue) >= count:
                break

    # 3. Fallback con canciones aleatorias si la biblioteca es pequena
    if len(queue) < count:
        more_res = _call_subsonic("getRandomSongs", {"size": count - len(queue)})
        songs = more_res.get("randomSongs", {}).get("song", [])
        for s in songs:
            sid = s.get("id")
            if sid and sid not in seen_ids:
                queue.append(s)
                seen_ids.add(sid)

    return queue


def save_remote_play_queue(
    queue: list[dict[str, Any]],
    current_song_id: str,
    position_ms: int = 0,
) -> bool:
    """Guarda la cola de reproduccion completa y la posicion actual en Navidrome."""
    if not queue:
        return False

    base_params = {
        "u": NAVIDROME_USER,
        "s": NAVIDROME_SALT,
        "t": NAVIDROME_TOKEN,
        "v": "1.16.1",
        "c": "jota",
        "f": "json",
        "current": current_song_id,
        "position": position_ms,
    }
    query_parts = [urllib.parse.urlencode(base_params)]
    for s in queue:
        sid = s.get("id")
        if sid:
            query_parts.append(f"id={urllib.parse.quote(sid)}")

    full_query = "&".join(query_parts)
    url = f"{NAVIDROME_URL.rstrip('/')}/rest/savePlayQueue.view?{full_query}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Jota/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("subsonic-response", {}).get("status") == "ok"
    except Exception as e:
        logger.debug("Error guardando cola en Navidrome: %s", e)
        return False


def get_navidrome_player_status() -> dict[str, Any] | None:
    """Devuelve el estado de reproduccion interno de Navidrome si esta activo."""
    global _active_proc, _current_queue, _current_index, _is_paused

    if _active_proc is None:
        return None

    if _active_proc.poll() is not None:
        # El proceso termino (la pista acabo)
        return {"available": True, "status": "Stopped", "player": "Navidrome (Jota)"}

    if not _current_queue or _current_index >= len(_current_queue):
        return None

    current_song = _current_queue[_current_index]
    status_str = "Paused" if _is_paused else "Playing"
    return {
        "available": True,
        "status": status_str,
        "player": "Navidrome (Jota)",
        "title": current_song.get("title", ""),
        "artist": current_song.get("artist", ""),
        "album": current_song.get("album", ""),
        "duration": current_song.get("duration", 0),
        "song_id": current_song.get("id", ""),
    }


def stop_navidrome_player() -> None:
    """Detiene cualquier reproductor de audio activo de Jota."""
    global _active_proc, _is_paused
    if _active_proc:
        try:
            _active_proc.terminate()
            _active_proc.wait(timeout=1.0)
        except Exception:
            try:
                _active_proc.kill()
            except Exception:
                pass
        _active_proc = None
    _is_paused = False


def pause_navidrome_player() -> None:
    """Pausa la reproduccion interna enviando senal SIGSTOP."""
    global _active_proc, _is_paused, _paused_elapsed_seconds
    if _active_proc and _active_proc.poll() is None and not _is_paused:
        try:
            import signal

            _active_proc.send_signal(signal.SIGSTOP)
            _is_paused = True
            _paused_elapsed_seconds += time.monotonic() - _start_timestamp
        except Exception as e:
            logger.debug("Error pausando ffplay: %s", e)


def resume_navidrome_player() -> None:
    """Reanuda la reproduccion interna enviando senal SIGCONT."""
    global _active_proc, _is_paused, _start_timestamp
    if _active_proc and _active_proc.poll() is None and _is_paused:
        try:
            import signal

            _active_proc.send_signal(signal.SIGCONT)
            _is_paused = False
            _start_timestamp = time.monotonic()
        except Exception as e:
            logger.debug("Error reanudando ffplay: %s", e)


def get_current_playback_position_ms() -> int:
    """Calcula la posicion de reproduccion actual en milisegundos."""
    global _start_timestamp, _paused_elapsed_seconds, _is_paused
    if _active_proc and _active_proc.poll() is None:
        if _is_paused:
            return int(_paused_elapsed_seconds * 1000)
        elapsed = _paused_elapsed_seconds + (time.monotonic() - _start_timestamp)
        return int(max(0.0, elapsed) * 1000)

    # Si se esta reproduciendo en otro reproductor MPRIS (como Feishin)
    if shutil.which("playerctl"):
        try:
            proc = subprocess.run(
                ["playerctl", "position"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                pos_sec = float(proc.stdout.strip())
                return int(pos_sec * 1000)
        except Exception:
            pass

    return 0


def play_navidrome_smart_radio(query: str) -> tuple[bool, str]:
    """
    Busca una cancion, crea una cola inteligente con canciones similares (radio)
    y la reproduce localmente en el PC sincronizandola en Navidrome.
    """
    global _active_proc, _current_queue, _current_index, _start_timestamp
    global _paused_elapsed_seconds, _is_paused

    clean_query = query.strip()
    if not clean_query:
        return False, "Por favor especifica que cancion o artista quieres escuchar."

    song = search_song(clean_query)
    if not song:
        return False, f"No encontre '{clean_query}' en tu biblioteca de Navidrome."

    # Construir cola inteligente con canciones recomendadas y similares
    queue = build_smart_radio_queue(song, count=15)
    _current_queue = queue
    _current_index = 0

    target_id = song.get("id", "")
    target_title = song.get("title", clean_query)
    target_artist = song.get("artist", "")

    # Persistir cola en el servidor Navidrome para sincronizacion multi-dispositivo
    save_remote_play_queue(queue, target_id, position_ms=0)

    # Detener reproduccion anterior y arrancar stream
    stop_navidrome_player()

    # Si hay otros reproductores MPRIS sonando (ej. Feishin), pausarlos
    if shutil.which("playerctl"):
        subprocess.run(["playerctl", "pause"], capture_output=True, check=False)

    stream_url = get_stream_url(target_id)
    if shutil.which("ffplay"):
        try:
            _active_proc = subprocess.Popen(
                [
                    "ffplay",
                    "-nodisp",
                    "-autoexit",
                    "-loglevel",
                    "quiet",
                    stream_url,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            _start_timestamp = time.monotonic()
            _paused_elapsed_seconds = 0.0
            _is_paused = False
        except Exception as e:
            logger.error("Error iniciando ffplay: %s", e)
            return False, "Error al reproducir audio en el sistema."

    msg = f"Reproduciendo {target_title}"
    if target_artist:
        msg += f" de {target_artist}"
    msg += " y emisora con canciones similares."
    return True, msg


def transfer_playback_to_phone() -> tuple[bool, str]:
    """
    Pausa la reproduccion en el PC, guarda la posicion exacta en Navidrome
    y envia la senal de handoff al telefono movil conectado.
    """
    global _current_queue, _current_index

    # 1. Obtener la cancion que esta sonando actualmente
    current_title = ""
    current_artist = ""
    current_song_id = ""
    pos_ms = get_current_playback_position_ms()

    # Inspeccionar reproductor interno
    internal_status = get_navidrome_player_status()
    if internal_status and internal_status.get("status") in ("Playing", "Paused"):
        current_title = internal_status.get("title", "")
        current_artist = internal_status.get("artist", "")
        current_song_id = internal_status.get("song_id", "")
        stop_navidrome_player()
    elif shutil.which("playerctl"):
        # Inspeccionar reproductor externo (Feishin, etc.)
        try:
            format_str = "{{title}}\t{{artist}}"
            proc_meta = subprocess.run(
                ["playerctl", "metadata", "--format", format_str],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if proc_meta.returncode == 0 and proc_meta.stdout.strip():
                parts = proc_meta.stdout.strip().split("\t")
                if len(parts) >= 1:
                    current_title = parts[0]
                if len(parts) >= 2:
                    current_artist = parts[1]
            subprocess.run(["playerctl", "pause"], capture_output=True, check=False)
        except Exception:
            pass

    if not current_title:
        return False, "No hay ninguna pista reproduciendose en el PC para transferir."

    # 2. Si no tenemos song_id todavia, buscarlo en Navidrome
    if not current_song_id:
        found_song = search_song(f"{current_title} {current_artist}".strip())
        if found_song:
            current_song_id = found_song.get("id", "")
            if not _current_queue:
                _current_queue = build_smart_radio_queue(found_song, count=10)

    if current_song_id:
        save_remote_play_queue(_current_queue, current_song_id, position_ms=pos_ms)

    # 3. Notificar al telefono movil a traves del Bridge
    stream_url = get_stream_url(current_song_id) if current_song_id else ""
    handoff_payload = {
        "title": current_title,
        "artist": current_artist,
        "song_id": current_song_id,
        "position_ms": pos_ms,
        "stream_url": stream_url,
    }

    # Llamar al Bridge local
    try:
        import asyncio

        from bridge.phone_manager import phone_manager

        # Si hay un bucle de eventos corriendo, usarlo; sino crear uno puntual
        try:
            asyncio.get_running_loop()
            asyncio.create_task(phone_manager.send_media_handoff(handoff_payload))
        except RuntimeError:
            asyncio.run(phone_manager.send_media_handoff(handoff_payload))
    except Exception as e:
        logger.debug("No se pudo enviar handoff directamente por phone_manager: %s", e)

    msg = f"Reproduccion transferida al movil: continuando {current_title}"
    if current_artist:
        msg += f" de {current_artist}"
    msg += "."
    return True, msg


def mark_current_song_favorite() -> tuple[bool, str]:
    """
    Marca la pista que esta sonando actualmente como favorita en Navidrome.
    """
    current_title = ""
    current_artist = ""
    current_song_id = ""

    # 1. Inspeccionar reproductor interno
    internal_status = get_navidrome_player_status()
    if internal_status and internal_status.get("status") in ("Playing", "Paused"):
        current_title = internal_status.get("title", "")
        current_artist = internal_status.get("artist", "")
        current_song_id = internal_status.get("song_id", "")
    elif shutil.which("playerctl"):
        try:
            format_str = "{{title}}\t{{artist}}"
            proc_meta = subprocess.run(
                ["playerctl", "metadata", "--format", format_str],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if proc_meta.returncode == 0 and proc_meta.stdout.strip():
                parts = proc_meta.stdout.strip().split("\t")
                if len(parts) >= 1:
                    current_title = parts[0]
                if len(parts) >= 2:
                    current_artist = parts[1]
        except Exception:
            pass

    if not current_title and not current_song_id:
        return False, "No hay ninguna cancion reproduciendose para marcar como favorita."

    if not current_song_id:
        found_song = search_song(f"{current_title} {current_artist}".strip())
        if found_song:
            current_song_id = found_song.get("id", "")

    if not current_song_id:
        return False, f"No se encontro el identificador de '{current_title}' en Navidrome."

    res = _call_subsonic("star", {"id": current_song_id})
    if res.get("status") == "ok":
        name_display = current_title or "Pista actual"
        return True, f"'{name_display}' anadida a favoritos en Navidrome."
    return False, "No se pudo marcar la cancion como favorita en Navidrome."


def cast_current_song_to_tv(target: str = "tele") -> tuple[bool, str]:
    """
    Emite la cancion que esta sonando en el PC directamente hacia la television mediante catt.
    """
    from jota.tools.cast import cast_media

    # Si hay reproduccion interna, detenerla o pausarla
    internal_status = get_navidrome_player_status()
    current_song_id = ""
    current_title = ""
    if internal_status and internal_status.get("status") in ("Playing", "Paused"):
        current_song_id = internal_status.get("song_id", "")
        current_title = internal_status.get("title", "")
        stop_navidrome_player()
    elif shutil.which("playerctl"):
        try:
            format_str = "{{title}}\t{{artist}}"
            proc_meta = subprocess.run(
                ["playerctl", "metadata", "--format", format_str],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if proc_meta.returncode == 0 and proc_meta.stdout.strip():
                parts = proc_meta.stdout.strip().split("\t")
                if len(parts) >= 1:
                    current_title = parts[0]
                if len(parts) >= 2:
                    current_artist = parts[1]
                    found = search_song(f"{current_title} {current_artist}".strip())
                    if found:
                        current_song_id = found.get("id", "")
            subprocess.run(["playerctl", "pause"], capture_output=True, check=False)
        except Exception:
            pass

    stream_url = get_stream_url(current_song_id) if current_song_id else ""
    return cast_media(target=target, media_url=stream_url)


"""Herramienta de busqueda web con Google y navegador Firefox."""

import logging
import re
import shutil
import subprocess
import urllib.parse

from jota.config import BROWSER_BIN, WEB_SEARCH_URL

logger = logging.getLogger(__name__)


def clean_search_query(query: str) -> str:
    """Limpia la consulta de busqueda eliminando prefijos de comando."""
    text = query.strip()
    # Eliminar prefijos habituales
    text = re.sub(
        r"^(por favor\s+|puedes\s+)?(busca|buscame|buscar|encuentra)\s+"
        r"(en\s+(la\s+)?(web|google|internet))\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"^(por favor\s+|puedes\s+)?(busca|buscame|buscar|encuentra)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Si tenia un sufijo "en la web" / "en google"
    text = re.sub(
        r"\s+(en\s+(la\s+)?(web|google|internet))$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Limpiar comillas extras
    text = text.strip("\"' ")
    return text


def open_web_search(raw_query: str) -> tuple[bool, str]:
    """
    Abre una busqueda en Google dentro del navegador web (Firefox).
    Devuelve (exito, mensaje_para_tts).
    """
    query = clean_search_query(raw_query)
    if not query:
        return False, "No se especifico que buscar en la web."

    url = f"{WEB_SEARCH_URL}{urllib.parse.quote_plus(query)}"
    logger.info("Realizando busqueda web para %r -> %s", query, url)

    browser = shutil.which(BROWSER_BIN) or shutil.which("xdg-open")
    if not browser:
        err_msg = "No se encontro ningun navegador web para abrir la busqueda."
        logger.error(err_msg)
        return False, err_msg

    try:
        subprocess.Popen(
            [browser, url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        msg = f"Buscando en la web: {query}."
        logger.info(msg)
        return True, msg
    except Exception as exc:
        logger.exception("Error al abrir navegador para busqueda: %s", exc)
        return False, "Ocurrio un fallo al abrir la busqueda en la web."

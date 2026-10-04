"""Herramienta para consultar fecha y hora actual del sistema en lenguaje natural."""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DIAS_SEMANA = [
    "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"
]

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]


def get_current_time(mode: str = "time") -> tuple[bool, str]:
    """
    Devuelve la hora o fecha actual del sistema formateada en lenguaje natural para TTS.
    Modos:
      - 'time': 'Son las 14:45.'
      - 'date': 'Hoy es domingo, 4 de octubre de 2026.'
      - 'full': 'Hoy es domingo, 4 de octubre de 2026 y son las 14:45.'
    """
    now = datetime.now()
    dia_str = DIAS_SEMANA[now.weekday()]
    mes_str = MESES[now.month - 1]
    hora_str = now.strftime("%H:%M")

    clean_mode = mode.lower().strip()
    if clean_mode in ("date", "dia", "fecha"):
        msg = f"Hoy es {dia_str}, {now.day} de {mes_str} de {now.year}."
    elif clean_mode in ("full", "completo", "todo"):
        msg = f"Hoy es {dia_str}, {now.day} de {mes_str} de {now.year} y son las {hora_str}."
    else:
        msg = f"Son las {hora_str}."

    logger.info("Consulta temporal (%s): %s", clean_mode, msg)
    return True, msg

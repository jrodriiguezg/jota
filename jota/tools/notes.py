"""Gestion de notas rapidas y recordatorios en archivo local."""

import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

NOTES_FILE = Path.home() / ".local" / "share" / "jota" / "notes.md"


def _ensure_notes_file() -> Path:
    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not NOTES_FILE.exists():
        NOTES_FILE.write_text("# Notas de Jota\n\n", encoding="utf-8")
    return NOTES_FILE


def add_note(text: str) -> tuple[bool, str]:
    """Anade una nueva nota con marca de tiempo."""
    clean = text.strip()
    if not clean:
        return False, "La nota no puede estar vacia."

    file = _ensure_notes_file()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"- [{now_str}] {clean}\n"

    try:
        with file.open("a", encoding="utf-8") as f:
            f.write(line)
        return True, f"Nota guardada: {clean}"
    except Exception as e:
        logger.error("Error guardando nota: %s", e)
        return False, f"Error al guardar la nota: {e}"


def list_notes(limit: int = 5) -> tuple[bool, str]:
    """Lee las ultimas notas registradas."""
    file = _ensure_notes_file()
    try:
        content = file.read_text(encoding="utf-8").splitlines()
        notes = [line.strip() for line in content if line.strip().startswith("- [")]
        if not notes:
            return True, "No tienes ninguna nota guardada."

        recent = notes[-limit:]
        items = "; ".join(n[2:] for n in recent)
        return True, f"Tus ultimas notas son: {items}."
    except Exception as e:
        logger.error("Error leyendo notas: %s", e)
        return False, f"Error al leer las notas: {e}"


def clear_notes() -> tuple[bool, str]:
    """Limpia el archivo de notas."""
    file = _ensure_notes_file()
    try:
        file.write_text("# Notas de Jota\n\n", encoding="utf-8")
        return True, "Todas las notas han sido borradas."
    except Exception as e:
        logger.error("Error borrando notas: %s", e)
        return False, f"Error al borrar las notas: {e}"

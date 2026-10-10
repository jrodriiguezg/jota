"""
Indicador de bandeja del sistema (System Tray / AppIndicator) para Jota en Wayland.
Se integra en la barra Waybar mediante el protocolo StatusNotifierItem.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

try:
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3, GLib, Gtk
except Exception:
    AppIndicator3 = None
    Gtk = None
    GLib = None

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "icons"
ICON_PATH = ASSETS_DIR / "jota_64.png"
if not ICON_PATH.exists():
    ICON_PATH = ASSETS_DIR / "jota.png"


class JotaTrayIndicator:
    """Gestiona el icono en la bandeja del sistema y su menu interactivo."""

    def __init__(self, orb_window: Any = None):
        self.orb_window = orb_window
        self.indicator: Any = None
        self.status_item: Any = None
        self.orb_toggle_item: Any = None

        if AppIndicator3 is None or Gtk is None:
            logger.warning(
                "AppIndicator3 no esta disponible en el entorno; "
                "el icono de bandeja no se mostrara."
            )
            return

        self._setup_indicator()

    def _setup_indicator(self) -> None:
        """Inicializa AppIndicator3 con el icono de Jota y construye el menu."""
        self.indicator = AppIndicator3.Indicator.new(
            "jota-tray",
            "jota",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        if ASSETS_DIR.exists():
            self.indicator.set_icon_theme_path(str(ASSETS_DIR.resolve()))
            self.indicator.set_icon_theme_path(str(ASSETS_DIR.resolve()))

        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Jota")

        menu = self._build_menu()
        self.indicator.set_menu(menu)
        logger.info("Icono de bandeja del sistema inicializado correctamente.")

    def _build_menu(self) -> Any:
        """Construye el menu contextual de la bandeja del sistema."""
        menu = Gtk.Menu()

        # Cabecera de la aplicacion
        title_item = Gtk.MenuItem(label="Jota — Asistente de Voz")
        title_item.set_sensitive(False)
        menu.append(title_item)

        # Estado en tiempo real
        self.status_item = Gtk.MenuItem(label="Estado: Listo (en reposo)")
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)

        sep1 = Gtk.SeparatorMenuItem()
        menu.append(sep1)

        # Alternar visibilidad del orbe flotante
        self.orb_toggle_item = Gtk.CheckMenuItem(label="Mostrar orbe visual en pantalla")
        if self.orb_window:
            self.orb_toggle_item.set_active(self.orb_window.get_visible())
        else:
            self.orb_toggle_item.set_active(True)
        self.orb_toggle_item.connect("toggled", self._on_toggle_orb)
        menu.append(self.orb_toggle_item)

        # Acceso rapido a archivo de escenas
        scenes_item = Gtk.MenuItem(label="Editar escenas (scenes.yaml)")
        scenes_item.connect("activate", self._on_edit_scenes)
        menu.append(scenes_item)

        # Ver registros de journalctl
        logs_item = Gtk.MenuItem(label="Ver registros en vivo (journalctl)")
        logs_item.connect("activate", self._on_view_logs)
        menu.append(logs_item)

        sep2 = Gtk.SeparatorMenuItem()
        menu.append(sep2)

        # Reiniciar servicio
        restart_item = Gtk.MenuItem(label="Reiniciar servicio Jota")
        restart_item.connect("activate", self._on_restart_service)
        menu.append(restart_item)

        # Detener servicio
        stop_item = Gtk.MenuItem(label="Detener servicio Jota")
        stop_item.connect("activate", self._on_stop_service)
        menu.append(stop_item)

        menu.show_all()
        return menu

    def set_state(self, state: str) -> None:
        """Actualiza el texto de estado en el menu segun la actividad de Jota."""
        if not self.status_item or GLib is None:
            return

        state_labels = {
            "idle": "Estado: Listo (en reposo)",
            "listening": "Estado: Escuchando...",
            "thinking": "Estado: Pensando orden...",
            "speaking": "Estado: Respondiendo...",
        }
        label_text = state_labels.get(state.lower(), f"Estado: {state.capitalize()}")

        def _update():
            if self.status_item:
                self.status_item.set_label(label_text)
            return False

        GLib.idle_add(_update)

    def _on_toggle_orb(self, widget: Any) -> None:
        """Muestra u oculta el orbe visual flotante."""
        if not self.orb_window:
            return

        if widget.get_active():
            self.orb_window.show_all()
        else:
            self.orb_window.hide()

    def _on_edit_scenes(self, _widget: Any) -> None:
        """Abre el archivo ~/.config/jota/scenes.yaml en el editor del sistema."""
        scenes_path = Path.home() / ".config" / "jota" / "scenes.yaml"
        if not scenes_path.exists():
            from jota.tools.scenes import ensure_scenes_file
            ensure_scenes_file()

        editor = os.getenv("EDITOR") or "xdg-open"
        try:
            subprocess.Popen(
                [editor, str(scenes_path)],
                start_new_session=True,
            )
        except Exception as e:
            logger.error("No se pudo abrir editor de escenas: %s", e)

    def _on_view_logs(self, _widget: Any) -> None:
        """Abre una ventana de terminal con journalctl siguiendo los logs de Jota."""
        term_candidates = ["kitty", "alacritty", "foot", "gnome-terminal", "konsole", "xterm"]
        found_term = None
        for term in term_candidates:
            if shutil.which(term):
                found_term = term
                break

        if not found_term:
            logger.warning("No se encontro un emulador de terminal disponible para ver logs.")
            return

        cmd = [found_term]
        if found_term in ("kitty", "alacritty", "foot"):
            cmd.extend(["-e", "journalctl", "--user", "-u", "jota", "-f"])
        elif found_term == "gnome-terminal":
            cmd.extend(["--", "journalctl", "--user", "-u", "jota", "-f"])
        else:
            cmd.extend(["-e", "journalctl", "--user", "-u", "jota", "-f"])

        try:
            subprocess.Popen(cmd, start_new_session=True)
        except Exception as e:
            logger.error("Error al abrir visor de registros: %s", e)

    def _on_restart_service(self, _widget: Any) -> None:
        """Reinicia el servicio de usuario systemd."""
        try:
            subprocess.Popen(
                ["systemctl", "--user", "restart", "jota.service"],
                start_new_session=True,
            )
        except Exception as e:
            logger.error("Error reiniciando servicio jota: %s", e)

    def _on_stop_service(self, _widget: Any) -> None:
        """Detiene el servicio de usuario systemd."""
        try:
            subprocess.Popen(
                ["systemctl", "--user", "stop", "jota.service"],
                start_new_session=True,
            )
        except Exception as e:
            logger.error("Error deteniendo servicio jota: %s", e)

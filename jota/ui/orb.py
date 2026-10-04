"""
Indicador visual de pantalla para Jota (Wayland / Hyprland).
Renderiza un orbe flotante animado en la esquina de la pantalla utilizando
Gtk 3.0, GtkLayerShell y Cairo con aceleracion y transparencia nativa.

Estados visuales:
  - idle:      Invisible / reposo (sin consumo de CPU).
  - listening: Orbe cian reactivo al volumen de voz con ondas de expansion.
  - thinking:  Orbe violeta cosmico con particulas de energia en orbita.
  - speaking:  Orbe esmeralda / turquesa con ondas ritmicas de habla.
"""

import argparse
import logging
import math
import signal
import socket
import sys
import threading
import time
from pathlib import Path

try:
    import gi
    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    import cairo
    from gi.repository import GLib, Gtk, GtkLayerShell
except Exception as exc:
    print(f"Error cargando dependencias graficas de Wayland: {exc}", file=sys.stderr)
    sys.exit(1)

from jota.config import (
    ORB_CORNER,
    ORB_FPS,
    ORB_MARGIN_X,
    ORB_MARGIN_Y,
    ORB_SIZE,
    ORB_SOCKET_PATH,
)

logger = logging.getLogger("jota.ui.orb")


class JotaOrbWindow(Gtk.Window):
    """Ventana overlay transparente nativa de Wayland con animacion Cairo."""

    def __init__(self, size: int = ORB_SIZE, corner: str = ORB_CORNER):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.size = size
        self.corner = corner

        # Estados de animacion
        self.state = "idle"
        self.current_alpha = 0.0
        self.target_alpha = 0.0
        self.voice_level = 0.0
        self.current_voice_level = 0.0
        self.start_time = time.time()

        # Configuracion de capa Wayland con GtkLayerShell
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)
        GtkLayerShell.set_exclusive_zone(self, 0)

        self._configure_anchors()

        # Transparencia completa de fondo RGBA
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_app_paintable(True)
        self.set_default_size(self.size, self.size)
        self.set_size_request(self.size, self.size)

        # Area de dibujo
        self.darea = Gtk.DrawingArea()
        self.darea.connect("draw", self.on_draw)
        self.add(self.darea)

        # Timer de animacion a 60 FPS
        self._interval_ms = max(10, 1000 // ORB_FPS)
        GLib.timeout_add(self._interval_ms, self._on_tick)

    def _configure_anchors(self) -> None:
        """Posiciona la ventana en la esquina configurada de la pantalla."""
        if self.corner == "bottom_left":
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM, ORB_MARGIN_Y)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, ORB_MARGIN_X)
        elif self.corner == "top_right":
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, ORB_MARGIN_Y)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, ORB_MARGIN_X)
        elif self.corner == "top_left":
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, ORB_MARGIN_Y)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, ORB_MARGIN_X)
        else:  # default "bottom_right"
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM, ORB_MARGIN_Y)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, ORB_MARGIN_X)

    def set_state(self, new_state: str, level: float = 0.0) -> None:
        """Actualiza el estado y el nivel de entrada de audio."""
        clean = new_state.lower().strip()
        if clean in ("listen", "listening", "grabar", "grabando"):
            self.state = "listening"
            self.target_alpha = 1.0
            self.show_all()
        elif clean in ("think", "thinking", "procesar", "pensando"):
            self.state = "thinking"
            self.target_alpha = 1.0
            self.show_all()
        elif clean in ("speak", "speaking", "hablar", "hablando"):
            self.state = "speaking"
            self.target_alpha = 1.0
            self.show_all()
        elif clean in ("idle", "hide", "ocultar", "off"):
            self.state = "idle"
            self.target_alpha = 0.0
        else:
            self.state = clean

        if level >= 0.0:
            self.voice_level = min(1.0, max(0.0, level))

    def set_voice_level(self, level: float) -> None:
        """Actualiza la intensidad del audio para reactividad visual."""
        self.voice_level = min(1.0, max(0.0, level))

    def _on_tick(self) -> bool:
        """Paso de tiempo del bucle de animacion."""
        # Interpolacion suave de opacidad (fade in / fade out)
        alpha_diff = self.target_alpha - self.current_alpha
        self.current_alpha += alpha_diff * 0.16

        # Interpolacion suave del nivel de voz
        lvl_diff = self.voice_level - self.current_voice_level
        self.current_voice_level += lvl_diff * 0.25

        if self.current_alpha > 0.005:
            self.darea.queue_draw()
        elif self.state == "idle" and self.current_alpha <= 0.005:
            self.current_alpha = 0.0
            self.hide()

        return True

    def on_draw(self, widget, cr: cairo.Context) -> bool:
        """Dibuja el orbe segun el estado y tiempo transcurrido."""
        # Limpieza absoluta del buffer a transparente
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        alpha = self.current_alpha
        if alpha <= 0.005:
            return True

        alloc = widget.get_allocation()
        cx = alloc.width / 2.0
        cy = alloc.height / 2.0
        t = time.time() - self.start_time
        base_r = 32.0

        if self.state == "listening":
            self._draw_listening_orb(cr, cx, cy, base_r, t, alpha)
        elif self.state == "thinking":
            self._draw_thinking_orb(cr, cx, cy, base_r, t, alpha)
        elif self.state == "speaking":
            self._draw_speaking_orb(cr, cx, cy, base_r, t, alpha)
        else:
            self._draw_idle_orb(cr, cx, cy, base_r, t, alpha)

        return True

    def _draw_listening_orb(
        self, cr: cairo.Context, cx: float, cy: float, base_r: float, t: float, alpha: float
    ) -> None:
        """Orbe en escucha: azul cian con halo pulsante reactivo al microfono."""
        lvl = self.current_voice_level
        pulse = math.sin(t * 4.0) * 2.0 + (lvl * 14.0)
        r = base_r + pulse

        # 1. Ondas de expansion reactivas
        wave1_phase = (t * 22.0) % 36.0
        w1_r = base_r + wave1_phase + (lvl * 8.0)
        w1_alpha = max(0.0, (1.0 - (wave1_phase / 36.0))) * 0.45 * alpha
        cr.arc(cx, cy, w1_r, 0, 2 * math.pi)
        cr.set_source_rgba(0.0, 0.85, 1.0, w1_alpha)
        cr.set_line_width(2.0)
        cr.stroke()

        wave2_phase = ((t * 22.0) + 18.0) % 36.0
        w2_r = base_r + wave2_phase + (lvl * 8.0)
        w2_alpha = max(0.0, (1.0 - (wave2_phase / 36.0))) * 0.35 * alpha
        cr.arc(cx, cy, w2_r, 0, 2 * math.pi)
        cr.set_source_rgba(0.2, 0.6, 1.0, w2_alpha)
        cr.set_line_width(1.5)
        cr.stroke()

        # 2. Halo ambiental exterior
        halo_r = r * 1.85
        halo = cairo.RadialGradient(cx, cy, r * 0.5, cx, cy, halo_r)
        halo.add_color_stop_rgba(0.0, 0.0, 0.85, 1.0, 0.5 * alpha)
        halo.add_color_stop_rgba(0.6, 0.1, 0.45, 0.95, 0.25 * alpha)
        halo.add_color_stop_rgba(1.0, 0.0, 0.2, 0.8, 0.0)
        cr.arc(cx, cy, halo_r, 0, 2 * math.pi)
        cr.set_source(halo)
        cr.fill()

        # 3. Nucleo del orbe tridimensional
        core = cairo.RadialGradient(cx - r * 0.3, cy - r * 0.3, 2, cx, cy, r)
        core.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.95 * alpha)
        core.add_color_stop_rgba(0.25, 0.0, 0.9, 1.0, 0.9 * alpha)
        core.add_color_stop_rgba(0.7, 0.08, 0.4, 0.9, 0.85 * alpha)
        core.add_color_stop_rgba(0.95, 0.02, 0.15, 0.6, 0.6 * alpha)
        core.add_color_stop_rgba(1.0, 0.0, 0.1, 0.5, 0.0)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.set_source(core)
        cr.fill()

        # 4. Brillo especular superior
        sheen = cairo.RadialGradient(
            cx - r * 0.35, cy - r * 0.35, 1, cx - r * 0.25, cy - r * 0.25, r * 0.5
        )
        sheen.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.8 * alpha)
        sheen.add_color_stop_rgba(1.0, 1.0, 1.0, 1.0, 0.0)
        cr.arc(cx - r * 0.3, cy - r * 0.3, r * 0.45, 0, 2 * math.pi)
        cr.set_source(sheen)
        cr.fill()

    def _draw_thinking_orb(
        self, cr: cairo.Context, cx: float, cy: float, base_r: float, t: float, alpha: float
    ) -> None:
        """Orbe en procesamiento: violeta cosmico con satellites de energia en rotacion."""
        pulse = math.sin(t * 3.0) * 2.5
        r = base_r + pulse

        # 1. Halo magico violeta / magenta
        halo_r = r * 1.8
        halo = cairo.RadialGradient(cx, cy, r * 0.4, cx, cy, halo_r)
        halo.add_color_stop_rgba(0.0, 0.85, 0.35, 1.0, 0.55 * alpha)
        halo.add_color_stop_rgba(0.5, 0.55, 0.15, 0.9, 0.3 * alpha)
        halo.add_color_stop_rgba(1.0, 0.2, 0.05, 0.5, 0.0)
        cr.arc(cx, cy, halo_r, 0, 2 * math.pi)
        cr.set_source(halo)
        cr.fill()

        # 2. Satelites de energia girando en orbita
        orbit_r = r + 9.0
        num_motes = 3
        for i in range(num_motes):
            angle = (t * 3.4) + (i * (2 * math.pi / num_motes))
            mx = cx + math.cos(angle) * orbit_r
            my = cy + math.sin(angle) * (orbit_r * 0.75)  # ligera perspectiva eliptica
            mote_r = 4.0 + math.sin(t * 6.0 + i) * 1.2

            mote_grad = cairo.RadialGradient(mx, my, 1, mx, my, mote_r * 2.2)
            mote_grad.add_color_stop_rgba(0.0, 1.0, 0.8, 1.0, 0.95 * alpha)
            mote_grad.add_color_stop_rgba(0.5, 0.9, 0.2, 0.8, 0.6 * alpha)
            mote_grad.add_color_stop_rgba(1.0, 0.6, 0.1, 0.7, 0.0)

            cr.arc(mx, my, mote_r * 2.2, 0, 2 * math.pi)
            cr.set_source(mote_grad)
            cr.fill()

        # 3. Nucleo violeta iridiscente
        core = cairo.RadialGradient(cx - r * 0.25, cy - r * 0.25, 2, cx, cy, r)
        core.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.95 * alpha)
        core.add_color_stop_rgba(0.25, 0.85, 0.35, 1.0, 0.9 * alpha)
        core.add_color_stop_rgba(0.65, 0.5, 0.1, 0.85, 0.85 * alpha)
        core.add_color_stop_rgba(0.95, 0.2, 0.05, 0.45, 0.6 * alpha)
        core.add_color_stop_rgba(1.0, 0.15, 0.0, 0.35, 0.0)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.set_source(core)
        cr.fill()

        # 4. Reflejo cristalino
        sheen = cairo.RadialGradient(
            cx - r * 0.35, cy - r * 0.35, 1, cx - r * 0.25, cy - r * 0.25, r * 0.5
        )
        sheen.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.85 * alpha)
        sheen.add_color_stop_rgba(1.0, 1.0, 1.0, 1.0, 0.0)
        cr.arc(cx - r * 0.3, cy - r * 0.3, r * 0.45, 0, 2 * math.pi)
        cr.set_source(sheen)
        cr.fill()

    def _draw_speaking_orb(
        self, cr: cairo.Context, cx: float, cy: float, base_r: float, t: float, alpha: float
    ) -> None:
        """Orbe al hablar: turquesa y esmeralda con modulacion de frecuencia vocal."""
        # Pulsacion cadente ritmica
        pulse = (math.sin(t * 6.5) * 0.5 + 0.5) * 6.0
        r = base_r + pulse

        # 1. Ondas concentricas armonicas
        for idx in range(3):
            phase = (t * 26.0 + idx * 12.0) % 32.0
            wr = base_r + phase
            wa = max(0.0, 1.0 - (phase / 32.0)) * 0.4 * alpha
            cr.arc(cx, cy, wr, 0, 2 * math.pi)
            cr.set_source_rgba(0.1, 0.95, 0.75, wa)
            cr.set_line_width(1.8)
            cr.stroke()

        # 2. Halo calido esmeralda / turquesa
        halo_r = r * 1.8
        halo = cairo.RadialGradient(cx, cy, r * 0.5, cx, cy, halo_r)
        halo.add_color_stop_rgba(0.0, 0.1, 0.95, 0.75, 0.5 * alpha)
        halo.add_color_stop_rgba(0.6, 0.0, 0.65, 0.7, 0.25 * alpha)
        halo.add_color_stop_rgba(1.0, 0.05, 0.25, 0.4, 0.0)
        cr.arc(cx, cy, halo_r, 0, 2 * math.pi)
        cr.set_source(halo)
        cr.fill()

        # 3. Nucleo esmeralda
        core = cairo.RadialGradient(cx - r * 0.3, cy - r * 0.3, 2, cx, cy, r)
        core.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.95 * alpha)
        core.add_color_stop_rgba(0.25, 0.2, 0.95, 0.75, 0.9 * alpha)
        core.add_color_stop_rgba(0.7, 0.0, 0.6, 0.65, 0.85 * alpha)
        core.add_color_stop_rgba(0.95, 0.02, 0.25, 0.35, 0.6 * alpha)
        core.add_color_stop_rgba(1.0, 0.0, 0.15, 0.2, 0.0)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.set_source(core)
        cr.fill()

        # 4. Reflejo
        sheen = cairo.RadialGradient(
            cx - r * 0.35, cy - r * 0.35, 1, cx - r * 0.25, cy - r * 0.25, r * 0.5
        )
        sheen.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.8 * alpha)
        sheen.add_color_stop_rgba(1.0, 1.0, 1.0, 1.0, 0.0)
        cr.arc(cx - r * 0.3, cy - r * 0.3, r * 0.45, 0, 2 * math.pi)
        cr.set_source(sheen)
        cr.fill()

    def _draw_idle_orb(
        self, cr: cairo.Context, cx: float, cy: float, base_r: float, t: float, alpha: float
    ) -> None:
        """Orbe en transicion de salida o reposo."""
        core = cairo.RadialGradient(cx, cy, 2, cx, cy, base_r)
        core.add_color_stop_rgba(0.0, 0.7, 0.8, 1.0, 0.4 * alpha)
        core.add_color_stop_rgba(1.0, 0.2, 0.3, 0.6, 0.0)
        cr.arc(cx, cy, base_r, 0, 2 * math.pi)
        cr.set_source(core)
        cr.fill()


class OrbSocketServer:
    """Servidor IPC Unix Socket para recibir comandos de Jota en tiempo real."""

    def __init__(self, window: JotaOrbWindow, socket_path: Path = ORB_SOCKET_PATH):
        self.window = window
        self.socket_path = socket_path
        self._running = False
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Arranca el listener de sockets en un hilo secundario."""
        if self._running:
            return

        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except Exception:
                pass

        self._running = True
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(self.socket_path))
        self._sock.listen(5)
        self._sock.settimeout(0.5)

        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        logger.info("Servidor Socket de Orbe activo en %s", self.socket_path)

    def stop(self) -> None:
        """Detiene el socket y limpia el archivo temporal."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except Exception:
                pass

    def _listen_loop(self) -> None:
        while self._running:
            try:
                conn, _ = self._sock.accept()
            except TimeoutError:
                continue
            except Exception:
                break

            threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

    def _handle_client(self, conn: socket.socket) -> None:
        with conn:
            buffer = ""
            while self._running:
                try:
                    data = conn.recv(1024)
                    if not data:
                        break
                    buffer += data.decode("utf-8", errors="ignore")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        self._process_command(line.strip())
                except Exception:
                    break

    def _process_command(self, cmd: str) -> None:
        if not cmd:
            return

        parts = cmd.split()
        verb = parts[0].upper()

        if verb == "STATE":
            state = parts[1] if len(parts) > 1 else "idle"
            level = float(parts[2]) if len(parts) > 2 else 0.0
            GLib.idle_add(self.window.set_state, state, level)
        elif verb == "LEVEL":
            level = float(parts[1]) if len(parts) > 1 else 0.0
            GLib.idle_add(self.window.set_voice_level, level)
        elif verb == "QUIT":
            GLib.idle_add(Gtk.main_quit)


def run_demo(window: JotaOrbWindow) -> None:
    """Simula una sesion interactiva ciclica para demostracion visual."""
    def _demo_loop():
        time.sleep(1.0)
        while True:
            # 1. Pulsacion de tecla Copilot / Escucha activa
            GLib.idle_add(window.set_state, "listening", 0.0)
            for i in range(30):
                # Simular modulacion de voz
                sim_lvl = abs(math.sin(i * 0.35)) * 0.8
                GLib.idle_add(window.set_voice_level, sim_lvl)
                time.sleep(0.1)

            # 2. Procesamiento / Pensando
            GLib.idle_add(window.set_state, "thinking", 0.0)
            time.sleep(2.5)

            # 3. Respuesta de voz / Hablando
            GLib.idle_add(window.set_state, "speaking", 0.5)
            time.sleep(3.5)

            # 4. Fin de respuesta / Reposo
            GLib.idle_add(window.set_state, "idle", 0.0)
            time.sleep(2.5)

    t = threading.Thread(target=_demo_loop, daemon=True)
    t.start()


def main() -> None:
    """Punto de entrada de consola para arrancar el orbe de Jota."""
    parser = argparse.ArgumentParser(
        description="Orbe indicador visual flotante para Jota en Wayland."
    )
    parser.add_argument(
        "--demo", action="store_true", help="Ejecuta ciclo de demostracion automatica."
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    window = JotaOrbWindow()
    server = OrbSocketServer(window)
    server.start()

    def _on_signal(signum, frame):
        server.stop()
        Gtk.main_quit()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    if args.demo:
        run_demo(window)

    window.show_all()
    if not args.demo:
        window.hide()

    try:
        Gtk.main()
    finally:
        server.stop()


if __name__ == "__main__":
    main()

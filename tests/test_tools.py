"""Tests del sistema de herramientas y enrutamiento de intenciones (Fase 2)."""

from unittest.mock import MagicMock, patch

from jota.tools.apps import _clean_app_query, launch_application, resolve_app_target
from jota.tools.media import playback_control, set_volume, toggle_mute
from jota.tools.router import (
    execute_tool,
    match_fast_intent,
    parse_llm_tool_call,
)
from jota.tools.screenshot import take_screenshot_to_clipboard
from jota.tools.search import clean_search_query, open_web_search


class TestFastIntentRouter:
    """Verifica el reconocimiento rapido de comandos comunes."""

    def test_volume_intents(self):
        assert match_fast_intent("sube el volumen") == ("volume_control", {"direction": "up"})
        assert match_fast_intent("subir volumen") == ("volume_control", {"direction": "up"})
        assert match_fast_intent("aumenta el sonido") == ("volume_control", {"direction": "up"})
        assert match_fast_intent("baja el volumen") == ("volume_control", {"direction": "down"})
        assert match_fast_intent("bajar volumen") == ("volume_control", {"direction": "down"})
        assert match_fast_intent("menos sonido") == ("volume_control", {"direction": "down"})
        assert match_fast_intent("silencia el audio") == ("volume_control", {"action": "mute"})
        assert match_fast_intent("mute") == ("volume_control", {"action": "mute"})

    def test_media_intents(self):
        assert match_fast_intent("pausa la musica") == ("media_control", {"action": "pause"})
        assert match_fast_intent("pausar reproduccion") == ("media_control", {"action": "pause"})
        assert match_fast_intent("para la cancion") == ("media_control", {"action": "pause"})
        assert match_fast_intent("reproduce") == ("media_control", {"action": "play"})
        assert match_fast_intent("reanuda la musica") == ("media_control", {"action": "play"})
        assert match_fast_intent("siguiente cancion") == ("media_control", {"action": "next"})
        assert match_fast_intent("cambia de cancion") == ("media_control", {"action": "next"})
        assert match_fast_intent("cancion anterior") == ("media_control", {"action": "previous"})

    def test_screenshot_intents(self):
        assert match_fast_intent("captura pantalla") == ("screenshot", {})
        assert match_fast_intent("haz una captura de pantalla") == ("screenshot", {})
        assert match_fast_intent("copia la pantalla en el portapapeles") == ("screenshot", {})
        assert match_fast_intent("screenshot") == ("screenshot", {})

    def test_web_search_intents(self):
        assert match_fast_intent("buscame en la web que es una vaca") == (
            "web_search",
            {"query": "que es una vaca"},
        )
        assert match_fast_intent("busca en google recetas de cocina") == (
            "web_search",
            {"query": "recetas de cocina"},
        )
        assert match_fast_intent("busca historia de linux en la web") == (
            "web_search",
            {"query": "historia de linux"},
        )

    def test_open_app_intents(self):
        assert match_fast_intent("abre el explorador de archivos") == (
            "open_app",
            {"name": "explorador de archivos"},
        )
        assert match_fast_intent("abre dolphin") == ("open_app", {"name": "dolphin"})
        assert match_fast_intent("abre el reproductor de musica") == (
            "open_app",
            {"name": "reproductor de musica"},
        )
        assert match_fast_intent("abre feishin") == ("open_app", {"name": "feishin"})
        assert match_fast_intent("abre feisfin") == ("open_app", {"name": "feishin"})

    def test_phonetic_stt_normalizations(self):
        # Confusiones foneticas habituales de Whisper
        # ("habla" o "a ver" por "abre", "terminar" por "terminal")
        assert match_fast_intent("habla terminal") == ("open_app", {"name": "terminal"})
        assert match_fast_intent("habla la terminal") == ("open_app", {"name": "terminal"})
        assert match_fast_intent("a ver a terminar") == ("open_app", {"name": "terminal"})
        assert match_fast_intent("a ver la terminal") == ("open_app", {"name": "terminal"})
        assert match_fast_intent("abre dolfin") == ("open_app", {"name": "dolphin"})

    def test_datetime_intents(self):
        assert match_fast_intent("que hora es") == ("get_current_time", {"mode": "time"})
        assert match_fast_intent("dime la hora") == ("get_current_time", {"mode": "time"})
        assert match_fast_intent("hora actual") == ("get_current_time", {"mode": "time"})
        assert match_fast_intent("que dia es hoy") == ("get_current_time", {"mode": "date"})
        assert match_fast_intent("que fecha es") == ("get_current_time", {"mode": "date"})
        assert match_fast_intent("en que dia estamos") == ("get_current_time", {"mode": "date"})

    def test_screen_and_workspace_intents(self):
        assert match_fast_intent("muestrame la pantalla del pc") == ("screenshot", {})
        assert match_fast_intent("ver la pantalla") == ("screenshot", {})
        assert match_fast_intent("pasa al escritorio 3") == ("switch_workspace", {"target": 3})
        assert match_fast_intent("pasad al escritorio 3") == ("switch_workspace", {"target": 3})
        assert match_fast_intent("cambia al escritorio 2") == ("switch_workspace", {"target": 2})
        assert match_fast_intent("mueve la ventana al escritorio 3") == (
            "move_to_workspace",
            {"target": 3},
        )
        assert match_fast_intent("que tiempo hace hoy una albacete") == (
            "get_weather",
            {"city": "Albacete"},
        )

    def test_non_tool_intent_returns_none(self):
        assert match_fast_intent("como estas hoy") is None
        assert match_fast_intent("cual es la capital de Francia") is None
        assert match_fast_intent("cuentame un chiste") is None


class TestLLMToolParser:
    """Verifica la extraccion de directivas TOOL: ... desde la salida del LLM."""

    def test_parse_volume(self):
        out = "TOOL: volume_control(action='up')\nSubo el volumen enseguida."
        assert parse_llm_tool_call(out) == ("volume_control", {"direction": "up"})

        out2 = "TOOL: volume_control(action='mute')"
        assert parse_llm_tool_call(out2) == ("volume_control", {"action": "mute"})

        # Tolerar salida de Qwen sin guion bajo (volumecontrol)
        out3 = "TOOL: volumecontrol(action='up')"
        assert parse_llm_tool_call(out3) == ("volume_control", {"direction": "up"})

    def test_parse_media(self):
        out = "TOOL: media_control(action='next')"
        assert parse_llm_tool_call(out) == ("media_control", {"action": "next"})

        out2 = "TOOL: mediacontrol(action='pause')"
        assert parse_llm_tool_call(out2) == ("media_control", {"action": "pause"})

    def test_parse_screenshot(self):
        out = "TOOL: screenshot()"
        assert parse_llm_tool_call(out) == ("screenshot", {})

        out_monitor = "TOOL: screen_monitor()\nMuestro la pantalla del PC."
        assert parse_llm_tool_call(out_monitor) == ("screenshot", {})

        out_show = "TOOL: show_screen()"
        assert parse_llm_tool_call(out_show) == ("screenshot", {})

    def test_parse_open_app(self):
        out = "TOOL: open_app(name='dolphin')"
        assert parse_llm_tool_call(out) == ("open_app", {"name": "dolphin"})

        out2 = "TOOL: openapp(name='terminal')"
        assert parse_llm_tool_call(out2) == ("open_app", {"name": "terminal"})

    def test_parse_web_search(self):
        out = "TOOL: web_search(query='que es una vaca')"
        assert parse_llm_tool_call(out) == ("web_search", {"query": "que es una vaca"})

        out2 = "TOOL: websearch(query='que es una vaca')"
        assert parse_llm_tool_call(out2) == ("web_search", {"query": "que es una vaca"})
        assert parse_llm_tool_call(out) == ("web_search", {"query": "que es una vaca"})

    def test_parse_datetime(self):
        out = "TOOL: get_current_time(mode='time')\nSon las 14:45."
        assert parse_llm_tool_call(out) == ("get_current_time", {"mode": "time"})

        out2 = "TOOL: date(mode='date')"
        assert parse_llm_tool_call(out2) == ("get_current_time", {"mode": "date"})

    def test_parse_no_tool(self):
        assert parse_llm_tool_call("Hola, soy Jota en que puedo ayudarte?") is None


class TestAppResolver:
    """Verifica la resolucion de aplicaciones por alias, mimes y nombres."""

    def test_clean_app_query(self):
        query = "abre el explorador de archivos por favor"
        assert _clean_app_query(query) == "explorador de archivos"
        assert _clean_app_query("lanza dolphin") == "dolphin"

    def test_resolve_custom_and_aliases(self):
        target, friendly = resolve_app_target("reproductor de musica")
        assert target == "org.jeffvli.feishin"
        assert friendly == "Reproductor de musica"

        target_feisfin, friendly_feisfin = resolve_app_target("feisfin")
        assert target_feisfin == "org.jeffvli.feishin"
        assert friendly_feisfin == "Feisfin"

    def test_clean_search_query(self):
        assert clean_search_query("buscame en la web que es una vaca") == "que es una vaca"
        assert clean_search_query("busca en google recetas faciles") == "recetas faciles"
        assert clean_search_query("que es la gravedad en la web") == "que es la gravedad"


class TestToolExecution:
    """Pruebas unitarias con mocks para ejecucion de herramientas de sistema."""

    @patch("jota.tools.media.shutil.which")
    @patch("jota.tools.media._run_cmd")
    def test_set_volume(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/wpctl"
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Volume: 0.80"
        mock_run.return_value = mock_proc

        ok, msg = set_volume("up")
        assert ok is True
        assert "80%" in msg or "subido" in msg

    @patch("jota.tools.media.shutil.which")
    @patch("jota.tools.media._run_cmd")
    def test_toggle_mute(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/wpctl"
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Volume: 0.80 [MUTED]"
        mock_run.return_value = mock_proc

        ok, msg = toggle_mute()
        assert ok is True
        assert "silenciado" in msg.lower()

    @patch("jota.tools.media.shutil.which")
    @patch("jota.tools.media._run_cmd")
    def test_playback_control(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/playerctl"
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        ok, msg = playback_control("pause")
        assert ok is True
        assert "pausada" in msg

    @patch("jota.tools.screenshot.shutil.which")
    @patch("jota.tools.screenshot.subprocess.run")
    def test_take_screenshot(self, mock_sub_run, mock_which):
        mock_which.return_value = "/usr/bin/grim"
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = b"fake_png_data"
        mock_sub_run.return_value = mock_res

        ok, msg = take_screenshot_to_clipboard()
        assert ok is True
        assert "portapapeles" in msg

    @patch("jota.tools.apps.shutil.which")
    @patch("jota.tools.apps.subprocess.run")
    def test_launch_app_gtk_launch(self, mock_sub_run, mock_which):
        mock_which.side_effect = lambda bin_name: f"/usr/bin/{bin_name}"
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_sub_run.return_value = mock_res

        ok, msg = launch_application("dolphin")
        assert ok is True
        assert "Dolphin" in msg

    @patch("jota.tools.search.shutil.which")
    @patch("jota.tools.search.subprocess.Popen")
    def test_open_web_search(self, mock_popen, mock_which):
        mock_which.return_value = "/usr/bin/firefox"
        ok, msg = open_web_search("que es una vaca")
        assert ok is True
        assert "que es una vaca" in msg
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert "firefox" in args[0]
        assert "google.com/search?q=" in args[1]


class TestSystemTools:
    """Verifica el enrutamiento y ejecucion de herramientas del sistema."""

    def test_parse_system_tools(self):
        assert parse_llm_tool_call("TOOL: lock_pc()") == ("lock_pc", {})
        assert parse_llm_tool_call("TOOL: system_power(action='suspend')") == (
            "system_power",
            {"action": "suspend", "confirmed": False},
        )
        assert parse_llm_tool_call(
            "TOOL: system_power(action='suspend', confirmed=True)"
        ) == (
            "system_power",
            {"action": "suspend", "confirmed": True},
        )
        assert parse_llm_tool_call("TOOL: close_active_window()") == (
            "close_active_window",
            {},
        )
        assert parse_llm_tool_call(
            "TOOL: send_notification(title='Jota', message='hola')"
        ) == ("send_notification", {"title": "Jota", "message": "hola"})
        assert parse_llm_tool_call("TOOL: pc_summary()") == ("pc_summary", {})

    @patch("jota.tools.system.subprocess.Popen")
    def test_execute_system_tools(self, mock_popen):
        ok, msg = execute_tool("lock_pc", {})
        assert ok is True
        assert "bloqueada" in msg

        # Sin confirmacion previa pide confirmacion
        ok, msg = execute_tool("system_power", {"action": "suspend"})
        assert ok is True
        assert "Estas seguro" in msg

        # Con confirmacion procede a suspender
        ok, msg = execute_tool("system_power", {"action": "suspend", "confirmed": True})
        assert ok is True
        assert "Suspendiendo" in msg

        ok, msg = execute_tool("send_notification", {"title": "Test", "message": "Msg"})
        assert ok is True
        assert "Notificacion" in msg

    def test_pc_summary_execution(self):
        ok, msg = execute_tool("pc_summary", {})
        assert ok is True
        assert "CPU" in msg


class TestExtendedTools:
    """Verifica enrutamiento y ejecucion de herramientas extendidas."""

    def test_parse_extended_tools(self):
        assert parse_llm_tool_call("TOOL: switch_workspace(target=2)") == (
            "switch_workspace",
            {"target": 2},
        )
        assert parse_llm_tool_call("TOOL: move_to_workspace(target=3)") == (
            "move_to_workspace",
            {"target": 3},
        )
        assert parse_llm_tool_call("TOOL: get_weather(city='Madrid')") == (
            "get_weather",
            {"city": "Madrid"},
        )
        assert parse_llm_tool_call(
            "TOOL: manage_notes(action='add', text='comprar pan')"
        ) == ("manage_notes", {"action": "add", "text": "comprar pan"})
        assert parse_llm_tool_call(
            "TOOL: set_timer(seconds=60, label='la pizza')"
        ) == ("set_timer", {"seconds": 60, "label": "la pizza"})

    @patch("jota.tools.workspace.subprocess.run")
    @patch("jota.tools.workspace.shutil.which")
    def test_workspace_tools(self, mock_which, mock_run):
        mock_which.return_value = "/usr/bin/hyprctl"
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res

        ok, msg = execute_tool("switch_workspace", {"target": 2})
        assert ok is True
        assert "espacio de trabajo 2" in msg

        ok, msg = execute_tool("move_to_workspace", {"target": 3})
        assert ok is True
        assert "espacio de trabajo 3" in msg

    def test_notes_tools(self, tmp_path, monkeypatch):
        test_file = tmp_path / "notes.md"
        monkeypatch.setattr("jota.tools.notes.NOTES_FILE", test_file)

        ok, msg = execute_tool("manage_notes", {"action": "add", "text": "comprar cafe"})
        assert ok is True
        assert "comprar cafe" in msg

        ok, msg = execute_tool("manage_notes", {"action": "list"})
        assert ok is True
        assert "comprar cafe" in msg

        ok, msg = execute_tool("manage_notes", {"action": "clear"})
        assert ok is True
        assert "borradas" in msg

    @patch("jota.tools.timer.threading.Thread")
    def test_timer_tool(self, mock_thread):
        ok, msg = execute_tool("set_timer", {"seconds": 120, "label": "la sopa"})
        assert ok is True
        assert "2 minutos" in msg
        mock_thread.return_value.start.assert_called_once()

    @patch("jota.tools.weather.httpx.Client")
    def test_weather_tool(self, mock_client_cls):
        mock_client = MagicMock()
        mock_resp_geo = MagicMock()
        mock_resp_geo.status_code = 200
        mock_resp_geo.json.return_value = {
            "results": [
                {"name": "Madrid", "latitude": 40.4, "longitude": -3.7, "country": "España"}
            ]
        }
        mock_resp_weather = MagicMock()
        mock_resp_weather.status_code = 200
        mock_resp_weather.json.return_value = {
            "current": {"temperature_2m": 22.5, "relative_humidity_2m": 45, "weather_code": 0}
        }
        mock_client.__enter__.return_value.get.side_effect = [
            mock_resp_geo,
            mock_resp_weather,
        ]
        mock_client_cls.return_value = mock_client

        ok, msg = execute_tool("get_weather", {"city": "Madrid"})
        assert ok is True
        assert "Madrid" in msg
        assert "22.5" in msg

    def test_datetime_tool(self):
        ok, msg = execute_tool("get_current_time", {"mode": "time"})
        assert ok is True
        assert "Son las" in msg

        ok, msg = execute_tool("get_current_time", {"mode": "date"})
        assert ok is True
        assert "Hoy es" in msg




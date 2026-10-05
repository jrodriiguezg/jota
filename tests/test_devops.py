"""Pruebas unitarias para las herramientas de DevOps y administracion de sistemas."""

from unittest.mock import MagicMock, patch

from jota.tools.devops import (
    container_action,
    git_status_action,
    kill_process_action,
    port_action,
    process_monitor_action,
)
from jota.tools.router import execute_tool, match_fast_intent, parse_llm_tool_call


class TestPortAction:
    """Verifica la inspeccion y liberacion de puertos."""

    def test_invalid_port(self):
        ok, msg = port_action(-1, "check")
        assert ok is False
        assert "no es valido" in msg

        ok2, msg2 = port_action(70000, "check")
        assert ok2 is False
        assert "no es valido" in msg2

    @patch("jota.tools.devops.shutil.which")
    @patch("jota.tools.devops.subprocess.run")
    def test_check_port_busy(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/ss"
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = 'users:(("node",pid=12345,fd=4))'
        mock_run.return_value = proc

        ok, msg = port_action(8080, "check")
        assert ok is True
        assert "ocupado por el proceso 'node'" in msg
        assert "12345" in msg

    @patch("jota.tools.devops.shutil.which")
    @patch("jota.tools.devops.subprocess.run")
    def test_check_port_free(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/ss"
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = ""
        mock_run.return_value = proc

        ok, msg = port_action(8080, "check")
        assert ok is True
        assert "puerto 8080 esta libre" in msg

    @patch("jota.tools.devops._get_process_on_port")
    @patch("jota.tools.devops.os.kill")
    def test_kill_port_success(self, mock_kill, mock_get_proc):
        # Primera llamada encuentra el proceso, segunda verifica que ya no esta
        mock_get_proc.side_effect = [("node", 12345), None]

        ok, msg = port_action(8080, "kill")
        assert ok is True
        assert "Puerto 8080 liberado" in msg
        assert "node" in msg
        mock_kill.assert_called()

    @patch("jota.tools.devops._get_process_on_port")
    def test_kill_port_already_free(self, mock_get_proc):
        mock_get_proc.return_value = None
        ok, msg = port_action(8080, "kill")
        assert ok is True
        assert "ya estaba libre" in msg

    @patch("jota.tools.devops._get_process_on_port")
    def test_kill_port_protected_pid(self, mock_get_proc):
        mock_get_proc.return_value = ("systemd", 1)
        ok, msg = port_action(80, "kill")
        assert ok is False
        assert "Por seguridad no se puede terminar" in msg


class TestContainerAction:
    """Verifica la gestion de contenedores Podman / Docker."""

    @patch("jota.tools.devops._detect_container_engine")
    def test_no_engine(self, mock_engine):
        mock_engine.return_value = None
        ok, msg = container_action("list")
        assert ok is False
        assert "No se encontro ningun motor" in msg

    @patch("jota.tools.devops._detect_container_engine")
    @patch("jota.tools.devops.subprocess.run")
    def test_list_containers_running(self, mock_run, mock_engine):
        mock_engine.return_value = "/usr/bin/podman"
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "postgres\nredis\n"
        mock_run.return_value = proc

        ok, msg = container_action("list")
        assert ok is True
        assert "postgres y redis" in msg

    @patch("jota.tools.devops._detect_container_engine")
    @patch("jota.tools.devops.subprocess.run")
    def test_list_containers_empty(self, mock_run, mock_engine):
        mock_engine.return_value = "/usr/bin/podman"
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = ""
        mock_run.return_value = proc

        ok, msg = container_action("list")
        assert ok is True
        assert "No hay ningun contenedor en ejecucion" in msg

    @patch("jota.tools.devops._detect_container_engine")
    @patch("jota.tools.devops.subprocess.run")
    def test_stop_container(self, mock_run, mock_engine):
        mock_engine.return_value = "/usr/bin/podman"
        proc = MagicMock()
        proc.returncode = 0
        mock_run.return_value = proc

        ok, msg = container_action("stop", "postgres")
        assert ok is True
        assert "detenido correctamente" in msg
        mock_run.assert_called_with(
            ["/usr/bin/podman", "stop", "postgres"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    @patch("jota.tools.devops._detect_container_engine")
    @patch("jota.tools.devops.subprocess.run")
    def test_restart_container(self, mock_run, mock_engine):
        mock_engine.return_value = "/usr/bin/podman"
        proc = MagicMock()
        proc.returncode = 0
        mock_run.return_value = proc

        ok, msg = container_action("restart", "redis")
        assert ok is True
        assert "reiniciado correctamente" in msg

    @patch("jota.tools.devops._detect_container_engine")
    @patch("jota.tools.devops.subprocess.run")
    def test_start_container(self, mock_run, mock_engine):
        mock_engine.return_value = "/usr/bin/podman"
        proc = MagicMock()
        proc.returncode = 0
        mock_run.return_value = proc

        ok, msg = container_action("start", "nginx")
        assert ok is True
        assert "iniciado correctamente" in msg


class TestProcessMonitorAndKill:
    """Verifica el monitor de recursos y terminacion de procesos."""

    @patch("jota.tools.devops.shutil.which")
    @patch("jota.tools.devops.subprocess.run")
    def test_top_cpu(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/ps"
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "COMMAND %CPU %MEM\nqwen2.5 45.2 2.1\nfirefox 12.0 8.0\nnode 5.0 1.2\n"
        mock_run.return_value = proc

        ok, msg = process_monitor_action("top_cpu")
        assert ok is True
        assert "mayor consumo de CPU son" in msg
        assert "qwen2.5 con 45.2%" in msg

    @patch("jota.tools.devops.shutil.which")
    @patch("jota.tools.devops.subprocess.run")
    def test_top_ram(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/ps"
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "COMMAND %CPU %MEM\nfirefox 12.0 15.4\nelectron 4.0 10.2\n"
        mock_run.return_value = proc

        ok, msg = process_monitor_action("top_ram")
        assert ok is True
        assert "mayor consumo de memoria son" in msg
        assert "firefox con 15.4%" in msg

    @patch("jota.tools.devops.os.kill")
    def test_kill_process_by_pid(self, mock_kill):
        ok, msg = kill_process_action("12345")
        assert ok is True
        assert "PID 12345 terminado" in msg
        mock_kill.assert_called()

    def test_kill_process_protected_pid(self):
        ok, msg = kill_process_action("1")
        assert ok is False
        assert "Por seguridad no se puede terminar" in msg

    def test_kill_process_protected_name(self):
        ok, msg = kill_process_action("hyprland")
        assert ok is False
        assert "Por seguridad no se puede terminar" in msg

    @patch("jota.tools.devops.shutil.which")
    @patch("jota.tools.devops.subprocess.run")
    def test_kill_process_by_name(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/pkill"
        proc = MagicMock()
        proc.returncode = 0
        mock_run.return_value = proc

        ok, msg = kill_process_action("node")
        assert ok is True
        assert "Proceso 'node' terminado" in msg


class TestGitStatusAction:
    """Verifica la consulta de estado de repositorio Git."""

    @patch("jota.tools.devops.shutil.which")
    def test_no_git(self, mock_which):
        mock_which.return_value = None
        ok, msg = git_status_action()
        assert ok is False
        assert "git no disponible" in msg

    @patch("jota.tools.devops.shutil.which")
    @patch("jota.tools.devops.subprocess.run")
    def test_git_status_clean(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/git"
        p_check = MagicMock(returncode=0)
        p_branch = MagicMock(returncode=0, stdout="main\n")
        p_status = MagicMock(returncode=0, stdout="")

        mock_run.side_effect = [p_check, p_branch, p_status]

        ok, msg = git_status_action()
        assert ok is True
        assert "el repositorio esta limpio" in msg
        assert "main" in msg

    @patch("jota.tools.devops.shutil.which")
    @patch("jota.tools.devops.subprocess.run")
    def test_git_status_changes(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/git"
        p_check = MagicMock(returncode=0)
        p_branch = MagicMock(returncode=0, stdout="bridge\n")
        p_status = MagicMock(returncode=0, stdout=" M file1.py\n?? file2.py\nA  file3.py\n")

        mock_run.side_effect = [p_check, p_branch, p_status]

        ok, msg = git_status_action()
        assert ok is True
        assert "1 archivo en staged" in msg
        assert "1 modificado" in msg
        assert "1 sin seguimiento" in msg


class TestDevOpsRouterIntegration:
    """Verifica que el enrutador reconozca las intenciones rapidas y llamadas del LLM."""

    def test_fast_intents_ports(self):
        assert match_fast_intent("que proceso esta usando el puerto 8080") == (
            "port_action",
            {"port": 8080, "action": "check"},
        )
        assert match_fast_intent("quien usa el puerto 3000") == (
            "port_action",
            {"port": 3000, "action": "check"},
        )
        assert match_fast_intent("puerto 8765") == (
            "port_action",
            {"port": 8765, "action": "check"},
        )
        assert match_fast_intent("libera el puerto 3000") == (
            "port_action",
            {"port": 3000, "action": "kill"},
        )
        assert match_fast_intent("mata lo que este en el puerto 5000") == (
            "port_action",
            {"port": 5000, "action": "kill"},
        )

    def test_fast_intents_containers(self):
        assert match_fast_intent("que contenedores estan corriendo") == (
            "container_action",
            {"action": "list"},
        )
        assert match_fast_intent("contenedores activos") == (
            "container_action",
            {"action": "list"},
        )
        assert match_fast_intent("para el contenedor de postgres") == (
            "container_action",
            {"action": "stop", "target": "postgres"},
        )
        assert match_fast_intent("reinicia el contenedor redis") == (
            "container_action",
            {"action": "restart", "target": "redis"},
        )
        assert match_fast_intent("arranca el contenedor de nginx") == (
            "container_action",
            {"action": "start", "target": "nginx"},
        )

    def test_fast_intents_processes(self):
        assert match_fast_intent("que proceso esta consumiendo mas ram") == (
            "process_monitor",
            {"action": "top_ram"},
        )
        assert match_fast_intent("procesos con mas ram") == (
            "process_monitor",
            {"action": "top_ram"},
        )
        assert match_fast_intent("que proceso se esta comiendo la cpu") == (
            "process_monitor",
            {"action": "top_cpu"},
        )
        assert match_fast_intent("procesos con mas cpu") == (
            "process_monitor",
            {"action": "top_cpu"},
        )
        assert match_fast_intent("mata el proceso con pid 1234") == (
            "kill_process",
            {"target": "1234"},
        )
        assert match_fast_intent("mata el proceso node") == (
            "kill_process",
            {"target": "node"},
        )

    def test_fast_intents_git(self):
        assert match_fast_intent("como esta el repo") == ("git_status", {})
        assert match_fast_intent("tengo cambios sin commitear") == ("git_status", {})
        assert match_fast_intent("git status") == ("git_status", {})

    def test_parse_llm_devops_tools(self):
        out1 = "TOOL: port_action(port=8080, action='check')\nConsultando el puerto."
        assert parse_llm_tool_call(out1) == ("port_action", {"port": 8080, "action": "check"})

        out2 = "TOOL: container_action(action='list')\nConsultando contenedores."
        assert parse_llm_tool_call(out2) == ("container_action", {"action": "list", "target": ""})

        out3 = "TOOL: container_action(action='stop', target='postgres')"
        assert parse_llm_tool_call(out3) == (
            "container_action",
            {"action": "stop", "target": "postgres"},
        )

        out4 = "TOOL: process_monitor(action='top_cpu')\nConsultando CPU."
        assert parse_llm_tool_call(out4) == ("process_monitor", {"action": "top_cpu"})

        out5 = "TOOL: kill_process(target='node')\nCerrando node."
        assert parse_llm_tool_call(out5) == ("kill_process", {"target": "node"})

        out6 = "TOOL: git_status()\nConsultando repositorio."
        assert parse_llm_tool_call(out6) == ("git_status", {"path": ""})

    def test_execute_tool_devops(self):
        with patch("jota.tools.devops.port_action") as mock_port:
            mock_port.return_value = (True, "Puerto libre.")
            ok, msg = execute_tool("port_action", {"port": 8080, "action": "check"})
            assert ok is True
            assert "Puerto libre" in msg

        with patch("jota.tools.devops.container_action") as mock_cont:
            mock_cont.return_value = (True, "Contenedores activos: postgres.")
            ok, msg = execute_tool("container_action", {"action": "list"})
            assert ok is True
            assert "postgres" in msg

        with patch("jota.tools.devops.process_monitor_action") as mock_proc:
            mock_proc.return_value = (True, "Top cpu: python.")
            ok, msg = execute_tool("process_monitor", {"action": "top_cpu"})
            assert ok is True
            assert "Top cpu" in msg

        with patch("jota.tools.devops.kill_process_action") as mock_kill:
            mock_kill.return_value = (True, "Proceso terminado.")
            ok, msg = execute_tool("kill_process", {"target": "node"})
            assert ok is True
            assert "terminado" in msg

        with patch("jota.tools.devops.git_status_action") as mock_git:
            mock_git.return_value = (True, "Repo limpio.")
            ok, msg = execute_tool("git_status", {})
            assert ok is True
            assert "Repo limpio" in msg

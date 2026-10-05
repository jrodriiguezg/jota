"""Herramientas para desarrollo, devops e inspeccion de sistema (Fase 2)."""

import logging
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CRITICAL_SYSTEM_PROCESSES = {
    "systemd",
    "systemd-logind",
    "init",
    "hyprland",
    "waybar",
    "pipewire",
    "wireplumber",
    "dbus-daemon",
    "dbus-broker",
    "jota",
    "jota-bridge",
    "polkitd",
    "sddm",
    "gdm",
    "kwin",
}


def _detect_container_engine() -> str | None:
    """Detecta el motor de contenedores disponible (podman o docker)."""
    for engine in ("podman", "docker"):
        bin_path = shutil.which(engine)
        if bin_path:
            try:
                res = subprocess.run(
                    [bin_path, "ps"],
                    capture_output=True,
                    timeout=2,
                    check=False,
                )
                if res.returncode == 0:
                    return bin_path
            except Exception:
                continue
    return shutil.which("podman") or shutil.which("docker")


def _get_process_on_port(port: int) -> tuple[str, int] | None:
    """Busca el proceso (nombre, PID) que escucha en un puerto TCP."""
    ss_bin = shutil.which("ss")
    if ss_bin:
        try:
            res = subprocess.run(
                [ss_bin, "-tlpn", f"sport = :{port}"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                # Formato: users:(("jota-bridge",pid=78790,fd=56))
                match = re.search(r'users:\(\("([^"]+)",pid=(\d+)', res.stdout)
                if match:
                    return match.group(1), int(match.group(2))
        except Exception as e:
            logger.debug("Fallo al consultar ss: %s", e)

    lsof_bin = shutil.which("lsof")
    if lsof_bin:
        try:
            res = subprocess.run(
                [lsof_bin, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                lines = res.stdout.strip().splitlines()
                if len(lines) > 1:
                    parts = lines[1].split()
                    if len(parts) >= 2:
                        return parts[0], int(parts[1])
        except Exception as e:
            logger.debug("Fallo al consultar lsof: %s", e)

    return None


def port_action(port: int, action: str = "check") -> tuple[bool, str]:
    """
    Inspecciona o libera un puerto de red.
    action: 'check' o 'kill' / 'free'
    """
    if port < 1 or port > 65535:
        return False, f"El puerto {port} no es valido (debe estar entre 1 y 65535)."

    norm_action = str(action).strip().lower()
    proc_info = _get_process_on_port(port)

    if norm_action in ("check", "status", "info", "consultar"):
        if proc_info:
            pname, pid = proc_info
            return True, f"El puerto {port} esta ocupado por el proceso '{pname}' con PID {pid}."
        return True, f"El puerto {port} esta libre."

    if norm_action in ("kill", "free", "liberar", "cerrar", "matar"):
        if not proc_info:
            return True, f"El puerto {port} ya estaba libre."

        pname, pid = proc_info
        if pid <= 1 or pid in (os.getpid(), os.getppid()):
            return False, f"Por seguridad no se puede terminar el proceso {pname} (PID {pid})."

        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.3)
            # Verificar si sigue escuchando
            if _get_process_on_port(port):
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.2)

            return True, f"Puerto {port} liberado. Se cerro el proceso '{pname}' con PID {pid}."
        except ProcessLookupError:
            return True, f"Puerto {port} liberado."
        except Exception as e:
            logger.error("Error al liberar puerto %d: %s", port, e)
            return False, f"No se pudo liberar el puerto {port}: {e}"

    return False, f"Accion '{action}' no reconocida para gestion de puertos."


def container_action(action: str = "list", target: str = "") -> tuple[bool, str]:
    """
    Gestiona contenedores Docker o Podman.
    action: 'list' (activos), 'stop', 'restart', 'start'
    """
    engine = _detect_container_engine()
    if not engine:
        return False, "No se encontro ningun motor de contenedores (ni Podman ni Docker)."

    engine_name = Path(engine).name
    norm_action = str(action).strip().lower()

    if norm_action in ("list", "status", "running", "listar"):
        try:
            res = subprocess.run(
                [engine, "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if res.returncode != 0:
                return False, f"Error al consultar contenedores en {engine_name}."

            containers = [c.strip() for c in res.stdout.strip().splitlines() if c.strip()]
            if not containers:
                return True, f"No hay ningun contenedor en ejecucion en {engine_name}."

            if len(containers) == 1:
                return True, f"Contenedor activo en {engine_name}: {containers[0]}."
            names_str = ", ".join(containers[:-1]) + " y " + containers[-1]
            return True, f"Contenedores activos en {engine_name}: {names_str}."
        except Exception as e:
            return False, f"Error al listar contenedores: {e}"

    clean_target = str(target).strip()
    if not clean_target:
        return False, "Debes especificar el nombre o identificador del contenedor."

    if norm_action in ("stop", "parar", "detener"):
        try:
            res = subprocess.run(
                [engine, "stop", clean_target],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if res.returncode == 0:
                return True, f"Contenedor '{clean_target}' detenido correctamente."
            return False, f"No se pudo detener el contenedor '{clean_target}'."
        except Exception as e:
            return False, f"Error al detener contenedor: {e}"

    if norm_action in ("restart", "reiniciar"):
        try:
            res = subprocess.run(
                [engine, "restart", clean_target],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if res.returncode == 0:
                return True, f"Contenedor '{clean_target}' reiniciado correctamente."
            return False, f"No se pudo reiniciar el contenedor '{clean_target}'."
        except Exception as e:
            return False, f"Error al reiniciar contenedor: {e}"

    if norm_action in ("start", "iniciar", "arrancar"):
        try:
            res = subprocess.run(
                [engine, "start", clean_target],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if res.returncode == 0:
                return True, f"Contenedor '{clean_target}' iniciado correctamente."
            return False, f"No se pudo iniciar el contenedor '{clean_target}'."
        except Exception as e:
            return False, f"Error al iniciar contenedor: {e}"

    return False, f"Accion '{action}' no reconocida para contenedores."


def process_monitor_action(action: str = "top_cpu") -> tuple[bool, str]:
    """
    Consulta los procesos con mayor consumo de CPU o memoria RAM.
    action: 'top_cpu' o 'top_ram'
    """
    norm_action = str(action).strip().lower()
    sort_flag = "-%mem" if "ram" in norm_action or "mem" in norm_action else "-%cpu"
    col_name = "memoria" if "ram" in norm_action or "mem" in norm_action else "CPU"

    ps_bin = shutil.which("ps")
    if not ps_bin:
        return False, "Comando ps no disponible en el sistema."

    try:
        res = subprocess.run(
            [ps_bin, "-eo", "comm,%cpu,%mem", f"--sort={sort_flag}"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return False, f"No se pudo obtener el uso de {col_name}."

        lines = res.stdout.strip().splitlines()
        if len(lines) <= 1:
            return False, "No hay informacion de procesos disponible."

        entries = []
        for line in lines[1:4]:  # Top 3
            parts = line.split()
            if len(parts) >= 3:
                comm = parts[0]
                cpu_val = parts[1]
                mem_val = parts[2]
                val = mem_val if col_name == "memoria" else cpu_val
                entries.append(f"{comm} con {val}%")

        if not entries:
            return False, f"No se pudo procesar el uso de {col_name}."

        if len(entries) == 1:
            text = entries[0]
        else:
            text = ", ".join(entries[:-1]) + " y " + entries[-1]

        return True, f"Los procesos con mayor consumo de {col_name} son: {text}."
    except Exception as e:
        logger.error("Error al consultar monitor de procesos: %s", e)
        return False, f"Error al consultar procesos: {e}"


def kill_process_action(target: str) -> tuple[bool, str]:
    """
    Termina un proceso por PID o nombre, protegiendo procesos criticos.
    """
    clean_target = str(target).strip()
    if not clean_target:
        return False, "Debes indicar el PID o nombre del proceso a terminar."

    # Si es un PID numerico
    if clean_target.isdigit():
        pid = int(clean_target)
        if pid <= 1 or pid in (os.getpid(), os.getppid()):
            return False, f"Por seguridad no se puede terminar el proceso con PID {pid}."

        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.3)
            try:
                os.kill(pid, 0)  # Verificar si sigue vivo
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            return True, f"Proceso con PID {pid} terminado."
        except ProcessLookupError:
            return False, f"No se encontro ningun proceso con PID {pid}."
        except Exception as e:
            return False, f"Error al terminar proceso {pid}: {e}"

    # Si es por nombre
    target_lower = clean_target.lower()
    for crit in CRITICAL_SYSTEM_PROCESSES:
        if target_lower == crit or target_lower.startswith(crit):
            return (
                False,
                f"Por seguridad no se puede terminar el proceso de sistema '{clean_target}'.",
            )

    pkill_bin = shutil.which("pkill")
    if not pkill_bin:
        return False, "Comando pkill no disponible."

    try:
        res = subprocess.run(
            [pkill_bin, "-f", clean_target],
            capture_output=True,
            timeout=3,
            check=False,
        )
        if res.returncode == 0:
            return True, f"Proceso '{clean_target}' terminado."
        if res.returncode == 1:
            return False, f"No se encontro ningun proceso llamado '{clean_target}'."
        return False, f"No se pudo terminar el proceso '{clean_target}'."
    except Exception as e:
        return False, f"Error al terminar proceso: {e}"


def git_status_action(path: str = "") -> tuple[bool, str]:
    """
    Consulta el estado del repositorio Git en la ruta indicada o en el proyecto actual.
    """
    git_bin = shutil.which("git")
    if not git_bin:
        return False, "Comando git no disponible."

    repo_dir = Path(path).expanduser().resolve() if path else Path.cwd()

    try:
        # Verificar si es repositorio
        check = subprocess.run(
            [git_bin, "rev-parse", "--is-inside-work-tree"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if check.returncode != 0:
            return False, f"La carpeta '{repo_dir.name}' no es un repositorio Git."

        # Obtener rama
        branch_res = subprocess.run(
            [git_bin, "branch", "--show-current"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        branch = branch_res.stdout.strip() or "HEAD"

        # Obtener cambios
        status_res = subprocess.run(
            [git_bin, "status", "--porcelain"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        lines = [line for line in status_res.stdout.strip().splitlines() if line.strip()]

        repo_name = repo_dir.name
        if not lines:
            return True, f"En la rama {branch} de {repo_name}, el repositorio esta limpio."

        modificados = sum(
            1 for item in lines if item.startswith(" M") or item.startswith("M ")
        )
        sin_seguimiento = sum(1 for item in lines if item.startswith("??"))
        agregados = sum(
            1 for item in lines if item.startswith("A ") or item.startswith("AM")
        )

        detalles = []
        if agregados:
            detalles.append(f"{agregados} archivo{'s' if agregados > 1 else ''} en staged")
        if modificados:
            detalles.append(f"{modificados} modificado{'s' if modificados > 1 else ''}")
        if sin_seguimiento:
            detalles.append(f"{sin_seguimiento} sin seguimiento")

        resumen = ", ".join(detalles) if detalles else f"{len(lines)} cambios"
        return True, f"En la rama {branch} de {repo_name}, hay {resumen}."

    except Exception as e:
        logger.error("Error al consultar git status en %s: %s", repo_dir, e)
        return False, f"Error al consultar el repositorio: {e}"

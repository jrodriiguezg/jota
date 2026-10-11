"""
Gestion de perfiles de energia y rendimiento para Jota.
Compatible con powerprofilesctl, tuned-adm y cpupower en distribuciones Linux.
"""

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


def _normalize_profile_target(target: str) -> str:
    """Traduce terminos coloquiales en espanol a categorias estandar."""
    clean = target.lower().strip()
    if clean in (
        "performance",
        "rendimiento",
        "potencia",
        "juego",
        "juegos",
        "maximo",
        "rapido",
        "acelerado",
    ):
        return "performance"
    if clean in (
        "power-saver",
        "powersave",
        "ahorro",
        "bateria",
        "economico",
        "bajo",
        "silencioso",
    ):
        return "powersave"
    if clean in ("balanced", "equilibrado", "normal", "medio", "estandar"):
        return "balanced"
    return clean


def _get_active_profile() -> str:
    """Detecta el perfil de energia activo mediante powerprofilesctl o tuned-adm."""
    # 1. Probar powerprofilesctl
    if shutil.which("powerprofilesctl"):
        try:
            res = subprocess.run(
                ["powerprofilesctl", "get"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass

    # 2. Probar tuned-adm
    if shutil.which("tuned-adm"):
        try:
            res = subprocess.run(
                ["tuned-adm", "active"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                # Formato: Current active profile: throughput-performance
                line = res.stdout.strip()
                if ":" in line:
                    return line.split(":", 1)[1].strip()
                return line
        except Exception:
            pass

    # 3. Probar lectura sysfs scaling_governor
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor") as f:
            gov = f.read().strip()
            if gov:
                return gov
    except Exception:
        pass

    return "desconocido"


def power_profile_control(action: str = "get", profile: str = "") -> tuple[bool, str]:
    """
    Gestiona los perfiles de energia del equipo.
    action: 'get' / 'status', o 'set'
    profile: 'performance', 'balanced', 'powersave'
    """
    clean_action = action.lower().strip()
    clean_profile = profile.lower().strip()

    if clean_action in ("get", "status", "info", "consultar", "") and not clean_profile:
        current = _get_active_profile()
        return True, f"El perfil de energia actual es {current}."

    target = _normalize_profile_target(clean_profile or clean_action)

    # 1. Aplicar con powerprofilesctl si existe
    if shutil.which("powerprofilesctl"):
        prof_map = {
            "performance": "performance",
            "balanced": "balanced",
            "powersave": "power-saver",
        }
        cmd_prof = prof_map.get(target, target)
        try:
            res = subprocess.run(
                ["powerprofilesctl", "set", cmd_prof],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            )
            if res.returncode == 0:
                name_es = {
                    "performance": "rendimiento",
                    "balanced": "equilibrado",
                    "powersave": "ahorro de energia",
                }.get(target, target)
                return True, f"Perfil de energia cambiado a {name_es}."
        except Exception as e:
            logger.debug("Fallo al invocar powerprofilesctl: %s", e)

    # 2. Aplicar con tuned-adm si existe
    if shutil.which("tuned-adm"):
        tuned_map = {
            "performance": "throughput-performance",
            "balanced": "balanced",
            "powersave": "powersave",
        }
        cmd_prof = tuned_map.get(target, target)
        try:
            res = subprocess.run(
                ["tuned-adm", "profile", cmd_prof],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if res.returncode == 0:
                name_es = {
                    "performance": "rendimiento",
                    "balanced": "equilibrado",
                    "powersave": "ahorro de energia",
                }.get(target, target)
                return True, f"Perfil energetico cambiado a {name_es} mediante Tuned."
        except Exception as e:
            logger.debug("Fallo al invocar tuned-adm: %s", e)

    # 3. Aplicar con cpupower si existe
    if shutil.which("cpupower"):
        gov_map = {
            "performance": "performance",
            "balanced": "schedutil",
            "powersave": "powersave",
        }
        cmd_gov = gov_map.get(target, "powersave")
        try:
            res = subprocess.run(
                ["cpupower", "frequency-set", "-g", cmd_gov],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            )
            if res.returncode == 0:
                return True, f"Gobernador de CPU ajustado a {cmd_gov}."
        except Exception as e:
            logger.debug("Fallo al invocar cpupower: %s", e)

    return (
        False,
        "No se encontro un gestor de perfiles de energia compatible (powerprofilesctl/tuned-adm).",
    )

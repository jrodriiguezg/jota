"""
Herramienta de verificacion de paquetes y software en el sistema.
Permite consultar la presencia o la version de cualquier comando, binario,
paquete RPM, Flatpak, kernel o distribucion Linux.
"""

import logging
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Mapeo de nombres coloquiales o paquetes a nombres de binarios en PATH
PACKAGE_ALIASES: dict[str, list[str]] = {
    "golang": ["go"],
    "go": ["go"],
    "python": ["python3", "python"],
    "python3": ["python3", "python"],
    "python2": ["python2"],
    "java": ["java"],
    "jdk": ["java", "javac"],
    "openjdk": ["java"],
    "rust": ["rustc", "cargo"],
    "rustc": ["rustc"],
    "cargo": ["cargo"],
    "node": ["node", "nodejs"],
    "nodejs": ["node", "nodejs"],
    "npm": ["npm"],
    "pnpm": ["pnpm"],
    "yarn": ["yarn"],
    "bun": ["bun"],
    "deno": ["deno"],
    "ruby": ["ruby"],
    "php": ["php"],
    "git": ["git"],
    "docker": ["docker"],
    "podman": ["podman"],
    "ripgrep": ["rg", "ripgrep"],
    "rg": ["rg"],
    "neovim": ["nvim", "neovim"],
    "nvim": ["nvim"],
    "vim": ["vim"],
    "gcc": ["gcc"],
    "g++": ["g++"],
    "clang": ["clang"],
    "clang++": ["clang++"],
    "c++": ["g++", "clang++"],
    "cpp": ["g++", "clang++"],
    "c": ["gcc", "clang"],
    "ffmpeg": ["ffmpeg"],
    "curl": ["curl"],
    "wget": ["wget"],
    "bash": ["bash"],
    "zsh": ["zsh"],
    "fish": ["fish"],
    "hyprland": ["Hyprland", "hyprctl"],
    "waybar": ["waybar"],
    "pipewire": ["pipewire", "wpctl"],
    "wireplumber": ["wireplumber", "wpctl"],
    "postgresql": ["psql", "postgres"],
    "postgres": ["psql", "postgres"],
    "mysql": ["mysql", "mariadb"],
    "mariadb": ["mariadb", "mysql"],
}


def _run_cmd(cmd: list[str], timeout: float = 2.5) -> subprocess.CompletedProcess[str]:
    """Ejecuta un comando del sistema de forma segura con timeout."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _get_os_info() -> str | None:
    """Obtiene el nombre y version de la distribucion desde /etc/os-release."""
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return None
    try:
        content = os_release.read_text(encoding="utf-8")
        match_pretty = re.search(r'^PRETTY_NAME=["\']?(.*?)["\']?$', content, re.MULTILINE)
        if match_pretty and match_pretty.group(1).strip():
            return match_pretty.group(1).strip()
        match_name = re.search(r'^NAME=["\']?(.*?)["\']?$', content, re.MULTILINE)
        match_ver = re.search(r'^VERSION=["\']?(.*?)["\']?$', content, re.MULTILINE)
        if match_name:
            n = match_name.group(1).strip()
            v = match_ver.group(1).strip() if match_ver else ""
            return f"{n} {v}".strip()
    except Exception as e:
        logger.debug("Error leyendo /etc/os-release: %s", e)
    return None


def _get_kernel_info() -> str | None:
    """Obtiene la version del kernel de Linux usando uname -r."""
    try:
        proc = _run_cmd(["uname", "-r"])
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception as e:
        logger.debug("Error consultando kernel: %s", e)
    return None


def _extract_binary_version(binary: str) -> str | None:
    """
    Intenta extraer la version de un binario ejecutable probando flags comunes.
    """
    commands: list[list[str]] = []
    if binary == "go":
        commands.append(["go", "version"])
    commands.extend([
        [binary, "--version"],
        [binary, "version"],
        [binary, "-version"],
        [binary, "-v"],
        [binary, "-V"],
    ])

    for cmd in commands:
        try:
            p = _run_cmd(cmd, timeout=2.0)
            raw = p.stdout.strip() or p.stderr.strip()
            if p.returncode == 0 and raw:
                first_line = raw.splitlines()[0].strip()
                # Limpiar texto innecesario como hashes largos o avisos de copyright
                clean = re.sub(r"\(build.*?\)", "", first_line).strip()
                clean = re.sub(r"Copyright.*$", "", clean, flags=re.IGNORECASE).strip()
                if clean:
                    return clean
        except Exception:
            continue
    return None


def _extract_rpm_version(package_name: str) -> str | None:
    """Consulta la version de un paquete RPM en Fedora si esta instalado."""
    if not shutil.which("rpm"):
        return None
    try:
        proc = _run_cmd(["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}\n", package_name], timeout=2.0)
        if proc.returncode == 0 and proc.stdout.strip() and "not installed" not in proc.stdout:
            first_ver = proc.stdout.strip().splitlines()[0].strip()
            return first_ver
    except Exception as e:
        logger.debug("Error consultando rpm %s: %s", package_name, e)
    return None


def _extract_flatpak_version(app_name: str) -> tuple[str, str] | None:
    """Consulta si una app esta instalada via Flatpak y retorna (app_id, version)."""
    if not shutil.which("flatpak"):
        return None
    try:
        proc = _run_cmd(["flatpak", "list", "--app", "--columns=application,version"], timeout=2.5)
        if proc.returncode == 0 and proc.stdout.strip():
            target_lower = app_name.lower().strip()
            for line in proc.stdout.strip().splitlines()[1:]:
                parts = line.split()
                if not parts:
                    continue
                app_id = parts[0]
                version = parts[1] if len(parts) > 1 else ""
                if target_lower in app_id.lower():
                    return app_id, version
    except Exception as e:
        logger.debug("Error consultando flatpak list: %s", e)
    return None


def check_package(name: str, check: str = "version") -> tuple[bool, str]:
    """
    Verifica la existencia o la version de un paquete o programa en el sistema.
    name: nombre o alias del paquete/comando (ej: 'python', 'go', 'java', 'docker', 'git').
    check: 'version' | 'installed'
    """
    clean_name = name.lower().strip()
    clean_name = re.sub(r"^[¿¡\s]+|[?!.,\s]+$", "", clean_name)
    clean_name = re.sub(r"^(del?\s+|el\s+|la\s+|los\s+|las\s+)", "", clean_name).strip()

    check_type = check.lower().strip()
    is_presence_check = check_type in ("installed", "presence", "exist", "esta", "instalado")

    if not clean_name:
        return False, "No se indico ningun paquete o comando a verificar."

    # 1. Caso especial: Kernel de Linux
    if clean_name in ("kernel", "linux", "kernel linux", "nucleo"):
        k_ver = _get_kernel_info()
        if is_presence_check:
            return True, "El kernel de Linux esta activo en el sistema."
        if k_ver:
            return True, f"La version del kernel de Linux es {k_ver}."
        return True, "El kernel de Linux esta en ejecucion en el equipo."

    # 2. Caso especial: Sistema Operativo / Distribucion
    os_keywords = (
        "sistema", "sistema operativo", "distro", "distribucion", "os", "so", "fedora"
    )
    if clean_name in os_keywords:
        os_info = _get_os_info()
        if os_info:
            return True, f"El sistema operativo instalado es {os_info}."
        return True, "El sistema operativo es Linux Fedora."

    # 3. Determinar lista de binarios candidatos
    candidates = PACKAGE_ALIASES.get(clean_name, [clean_name])
    if clean_name not in candidates:
        candidates.append(clean_name)

    # 4. Busqueda como binario en PATH (which)
    found_bin_path: str | None = None
    matched_binary: str | None = None
    for cand in candidates:
        loc = shutil.which(cand)
        if loc:
            found_bin_path = loc
            matched_binary = cand
            break

    if found_bin_path and matched_binary:
        if is_presence_check:
            msg = f"Si, {clean_name} esta instalado en el sistema en {found_bin_path}."
            logger.info(msg)
            return True, msg

        ver_str = _extract_binary_version(matched_binary)
        if not ver_str:
            rpm_ver = _extract_rpm_version(matched_binary) or _extract_rpm_version(clean_name)
            if rpm_ver:
                ver_str = f"version {rpm_ver}"

        if ver_str:
            msg = f"La version de {clean_name} en el sistema es {ver_str}."
        else:
            msg = f"{clean_name.capitalize()} esta instalado en {found_bin_path}."
        logger.info(msg)
        return True, msg

    # 5. Busqueda como paquete RPM en el sistema (por si no es ejecutable directo en PATH)
    for cand in candidates:
        rpm_ver = _extract_rpm_version(cand)
        if rpm_ver:
            if is_presence_check:
                msg = (
                    f"Si, el paquete {clean_name} esta instalado en el sistema "
                    f"(RPM version {rpm_ver})."
                )
            else:
                msg = f"La version del paquete {clean_name} en el sistema es {rpm_ver}."
            logger.info(msg)
            return True, msg

    # 6. Busqueda en Flatpaks instalados
    flatpak_match = _extract_flatpak_version(clean_name)
    if flatpak_match:
        app_id, flat_ver = flatpak_match
        ver_desc = f"version {flat_ver}" if flat_ver else f"ID {app_id}"
        if is_presence_check:
            msg = f"Si, {clean_name} esta instalado en el sistema via Flatpak ({ver_desc})."
        else:
            msg = f"La version de {clean_name} instalada via Flatpak es {ver_desc}."
        logger.info(msg)
        return True, msg

    # 7. No encontrado
    msg = f"{clean_name.capitalize()} no esta instalado en el sistema."
    logger.info(msg)
    return True, msg

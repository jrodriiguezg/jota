"""
Modulo de seguridad de red y validacion de tokens para Jota.
Garantiza que la comunicacion entre Hub, Satelites y Bridge ocurra unicamente
sobre interfaces autorizadas (red local privada y malla Tailscale) y con tokens validos.
"""

import hmac
import ipaddress
import logging
from typing import Any

logger = logging.getLogger("jota.security")

# Rangos de red permitidos para el cluster
# 100.64.0.0/10 es el rango asignado oficialmente a CGNAT y utilizado por Tailscale
TAILSCALE_IPV4_NETWORK = ipaddress.ip_network("100.64.0.0/10")
TAILSCALE_IPV6_NETWORK = ipaddress.ip_network("fd7a:115c:a1e0::/48")


def is_safe_cluster_ip(ip_str: str) -> bool:
    """
    Verifica si una direccion IP pertenece a una red privada segura,
    bucle local (loopback) o a la malla cifrada de Tailscale.
    Rechaza conexiones procedentes de la Internet publica.
    """
    if not ip_str:
        return False

    clean_ip = ip_str.strip()
    # Limpiar formato de IPv4 mapeada en IPv6 (ej. ::ffff:192.168.1.50)
    if clean_ip.startswith("::ffff:"):
        clean_ip = clean_ip[7:]

    try:
        ip = ipaddress.ip_address(clean_ip)
    except ValueError:
        return False

    # 1. Loopback (localhost)
    if ip.is_loopback:
        return True

    # 2. Redes privadas RFC 1918 (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16) y ULA IPv6
    if ip.is_private:
        return True

    # 3. Malla Tailscale (CGNAT 100.64.0.0/10 y rango IPv6)
    if ip.version == 4 and ip in TAILSCALE_IPV4_NETWORK:
        return True
    if ip.version == 6 and ip in TAILSCALE_IPV6_NETWORK:
        return True

    # 4. Direcciones de enlace local (link-local)
    if ip.is_link_local:
        return True

    return False


def verify_cluster_token(provided_token: str | None, expected_token: str | None) -> bool:
    """
    Compara el token proporcionado con el token esperado en tiempo constante
    para mitigar ataques de temporizacion (timing attacks).
    """
    if not provided_token or not expected_token:
        return False

    return hmac.compare_digest(str(provided_token).strip(), str(expected_token).strip())


def extract_token_from_headers(headers: dict[str, str]) -> str | None:
    """
    Extrae el token de autenticacion de los encabezados HTTP soportados:
    1. X-Jota-Token (estandar nuevo)
    2. X-Bridge-Key (retrocompatibilidad)
    3. Authorization: Bearer <token>
    """
    # Normalizar claves a minusculas
    norm_headers = {k.lower(): v for k, v in headers.items()}

    # 1. X-Jota-Token
    if "x-jota-token" in norm_headers:
        val = norm_headers["x-jota-token"].strip()
        if val:
            return val

    # 2. X-Bridge-Key (compatibilidad previa)
    if "x-bridge-key" in norm_headers:
        val = norm_headers["x-bridge-key"].strip()
        if val:
            return val

    # 3. Authorization: Bearer <token>
    if "authorization" in norm_headers:
        auth_val = norm_headers["authorization"].strip()
        if auth_val.lower().startswith("bearer "):
            token = auth_val[7:].strip()
            if token:
                return token

    return None


def validate_node_registration(
    node_id: str,
    hardware_fingerprint: str,
    known_nodes: dict[str, dict[str, Any]],
) -> tuple[bool, str]:
    """
    Valida el registro de un nodo contra el registro de nodos conocidos.
    Previene colisiones y suplantacion de identidad (spoofing).
    """
    if not node_id or not node_id.startswith("node_"):
        return False, "Identificador de nodo con formato invalido (debe iniciar con node_)."

    if not hardware_fingerprint or len(hardware_fingerprint) != 64:
        return False, "Huella de hardware invalida (debe ser un hash SHA-256 de 64 caracteres)."

    if node_id in known_nodes:
        existing = known_nodes[node_id]
        existing_fp = existing.get("hardware_fingerprint", "")
        if existing_fp and existing_fp != hardware_fingerprint:
            return (
                False,
                f"Conflicto de hardware: el nodo '{node_id}' ya esta registrado con una huella distinta.",
            )

    return True, "Validacion correcta."

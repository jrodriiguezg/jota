"""
Pruebas unitarias para el modulo jota.security.
"""

from jota.security import (
    extract_token_from_headers,
    is_safe_cluster_ip,
    validate_node_registration,
    verify_cluster_token,
)


def test_is_safe_cluster_ip_allowed_ranges():
    """Verifica que loopback, redes privadas y Tailscale son admitidas."""
    # Loopback
    assert is_safe_cluster_ip("127.0.0.1") is True
    assert is_safe_cluster_ip("::1") is True

    # RFC 1918 LAN
    assert is_safe_cluster_ip("192.168.1.100") is True
    assert is_safe_cluster_ip("10.0.0.15") is True
    assert is_safe_cluster_ip("172.16.0.2") is True
    assert is_safe_cluster_ip("::ffff:192.168.1.50") is True

    # Tailscale CGNAT
    assert is_safe_cluster_ip("100.64.0.1") is True
    assert is_safe_cluster_ip("100.85.176.113") is True
    assert is_safe_cluster_ip("100.127.255.254") is True


def test_is_safe_cluster_ip_rejected_public():
    """Verifica que direcciones IP de la Internet publica son rechazadas."""
    assert is_safe_cluster_ip("8.8.8.8") is False
    assert is_safe_cluster_ip("1.1.1.1") is False
    assert is_safe_cluster_ip("142.250.180.14") is False
    assert is_safe_cluster_ip("not-an-ip") is False
    assert is_safe_cluster_ip("") is False


def test_verify_cluster_token():
    """Verifica la validacion de token con proteccion contra timing attacks."""
    assert verify_cluster_token("mi_token_secreto", "mi_token_secreto") is True
    assert verify_cluster_token("token_invalido", "mi_token_secreto") is False
    assert verify_cluster_token(None, "mi_token_secreto") is False
    assert verify_cluster_token("mi_token_secreto", None) is False


def test_extract_token_from_headers():
    """Verifica extraccion de token desde diferentes cabeceras HTTP."""
    # 1. X-Jota-Token
    h1 = {"X-Jota-Token": "token-nuevo-123"}
    assert extract_token_from_headers(h1) == "token-nuevo-123"

    # 2. X-Bridge-Key
    h2 = {"X-Bridge-Key": "token-legado-456"}
    assert extract_token_from_headers(h2) == "token-legado-456"

    # 3. Authorization Bearer
    h3 = {"Authorization": "Bearer token-bearer-789"}
    assert extract_token_from_headers(h3) == "token-bearer-789"

    # 4. Sin token
    h4 = {"Content-Type": "application/json"}
    assert extract_token_from_headers(h4) is None


def test_validate_node_registration():
    """Verifica la validacion de huella de hardware al registrar nodos."""
    known_nodes = {
        "node_1111222233334444": {
            "name": "workstation-pc",
            "hardware_fingerprint": "a" * 64,
        }
    }

    # Registro valido de nodo existente con misma huella
    ok, _ = validate_node_registration("node_1111222233334444", "a" * 64, known_nodes)
    assert ok is True

    # Intento de suplantacion (mismo node_id pero huella diferente)
    ok, msg = validate_node_registration("node_1111222233334444", "b" * 64, known_nodes)
    assert ok is False
    assert "Conflicto de hardware" in msg

    # Nuevo nodo legitimo
    ok, _ = validate_node_registration("node_5555666677778888", "c" * 64, known_nodes)
    assert ok is True

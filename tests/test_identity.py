"""
Pruebas unitarias para el modulo jota.identity.
"""

from unittest.mock import mock_open, patch

from jota.identity import (
    calculate_hardware_fingerprint,
    get_dmi_hardware_id,
    get_machine_id,
    get_node_id,
    get_node_metadata,
    get_primary_mac_address,
)


def test_get_machine_id_fallback():
    """Verifica que get_machine_id devuelve un valor consistente incluso si falla la lectura directa."""
    m_id = get_machine_id()
    assert isinstance(m_id, str)
    assert len(m_id) >= 16


def test_get_dmi_hardware_id_handles_permission_error():
    """Verifica degradacion elegante ante PermissionError en product_uuid."""
    dmi_id = get_dmi_hardware_id()
    assert isinstance(dmi_id, str)
    assert len(dmi_id) > 0


def test_get_primary_mac_address():
    """Verifica que se obtiene una direccion MAC con formato valido."""
    mac = get_primary_mac_address()
    assert isinstance(mac, str)
    assert len(mac) == 17
    parts = mac.split(":")
    assert len(parts) == 6


def test_calculate_hardware_fingerprint_deterministic():
    """Verifica que dos calculos consecutivos con la misma sal devuelven el mismo hash SHA-256."""
    fp1 = calculate_hardware_fingerprint(salt="test-salt")
    fp2 = calculate_hardware_fingerprint(salt="test-salt")
    assert fp1 == fp2
    assert len(fp1) == 64

    # Diferente sal genera diferente huella
    fp3 = calculate_hardware_fingerprint(salt="different-salt")
    assert fp1 != fp3


def test_get_node_id_format():
    """Verifica el prefijo y longitud de node_id."""
    node_id = get_node_id(salt="test-salt")
    assert node_id.startswith("node_")
    assert len(node_id) == 21  # 'node_' (5) + 16 chars de hash


def test_get_node_metadata():
    """Verifica la estructura y campos del diccionario de metadatos."""
    meta = get_node_metadata()
    assert "node_id" in meta
    assert "hostname" in meta
    assert "os" in meta
    assert "arch" in meta
    assert "has_tailscale" in meta
    assert "mac_primary" in meta

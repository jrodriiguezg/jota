"""
Pruebas unitarias para el modulo jota.crypto.
"""

import pytest

from jota.crypto import (
    derive_key,
    decrypt_dict_fields,
    decrypt_string,
    encrypt_dict_fields,
    encrypt_string,
)


def test_derive_key_length():
    """Verifica que la derivacion de clave genera exactamente 32 bytes (256 bits)."""
    key = derive_key("mi_clave_secreta")
    assert isinstance(key, bytes)
    assert len(key) == 32


def test_encrypt_decrypt_roundtrip():
    """Verifica el ciclo completo de cifrado y descifrado de texto."""
    secret = "cluster_master_token_xyz"
    original_text = "super_secret_navidrome_password_123"

    encrypted = encrypt_string(original_text, secret)
    assert encrypted.startswith("enc:v1:")
    assert encrypted != original_text

    decrypted = decrypt_string(encrypted, secret)
    assert decrypted == original_text


def test_decrypt_with_wrong_key_fails():
    """Verifica que descifrar con una clave incorrecta lanza ValueError."""
    encrypted = encrypt_string("datos_confidenciales", "clave_correcta")
    with pytest.raises(ValueError, match="Fallo de autenticacion"):
        decrypt_string(encrypted, "clave_incorrecta")


def test_decrypt_corrupted_payload_fails():
    """Verifica deteccion de manipulacion o corrupcion en la carga util."""
    encrypted = encrypt_string("datos", "clave")
    # Alterar un caracter del final del payload base64
    corrupted = encrypted[:-2] + ("A" if encrypted[-2] != "A" else "B") + encrypted[-1]
    with pytest.raises(ValueError):
        decrypt_string(corrupted, "clave")


def test_backward_compatibility_plain_text():
    """Verifica que texto no cifrado se devuelve intacto sin error."""
    plain = "password_heredado_en_plano"
    result = decrypt_string(plain, "cualquier_clave")
    assert result == plain


def test_encrypt_decrypt_dict_fields():
    """Verifica cifrado selectivo de claves en un diccionario."""
    secret = "vault_key"
    payload = {
        "node_id": "node_12345",
        "api_token": "token_secreto_abc",
        "public_name": "Servidor Secundario",
        "auth_secret": "password_privada",
    }

    encrypted_dict = encrypt_dict_fields(payload, ["api_token", "auth_secret"], secret)
    assert encrypted_dict["node_id"] == "node_12345"
    assert encrypted_dict["public_name"] == "Servidor Secundario"
    assert encrypted_dict["api_token"].startswith("enc:v1:")
    assert encrypted_dict["auth_secret"].startswith("enc:v1:")

    decrypted_dict = decrypt_dict_fields(encrypted_dict, ["api_token", "auth_secret"], secret)
    assert decrypted_dict == payload

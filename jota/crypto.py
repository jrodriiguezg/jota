"""
Modulo de criptografia y proteccion de datos en reposo para Jota.
Proporciona cifrado autenticado de alta seguridad (AES-256-GCM) para campos sensibles
almacenados en la base de datos SQLite (tokens, claves API, credenciales de servicios).
"""

import base64
import hashlib
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DEFAULT_VAULT_SALT = b"jota-vault-salt-v1"
PAYLOAD_PREFIX = "enc:v1:"


def derive_key(secret: str | bytes, salt: bytes = DEFAULT_VAULT_SALT) -> bytes:
    """
    Deriva una clave criptografica simetrica de 256 bits (32 bytes)
    a partir de una contrasena o token mediante PBKDF2-HMAC-SHA256.
    """
    if isinstance(secret, str):
        secret_bytes = secret.encode("utf-8")
    else:
        secret_bytes = secret

    return hashlib.pbkdf2_hmac(
        "sha256",
        secret_bytes,
        salt,
        iterations=100_000,
        dklen=32,
    )


def encrypt_string(plaintext: str, secret: str | bytes) -> str:
    """
    Cifra un texto plano utilizando AES-256-GCM con un nonce aleatorio de 12 bytes.
    Devuelve un string con el formato 'enc:v1:<base64_payload>'.
    """
    if plaintext is None:
        return ""
    if not isinstance(plaintext, str):
        plaintext = str(plaintext)

    key = derive_key(secret) if not (isinstance(secret, bytes) and len(secret) == 32) else secret
    aesgcm = AESGCM(key)

    nonce = os.urandom(12)
    plaintext_bytes = plaintext.encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)

    combined = nonce + ciphertext
    b64_payload = base64.urlsafe_b64encode(combined).decode("ascii")
    return f"{PAYLOAD_PREFIX}{b64_payload}"


def decrypt_string(ciphertext: str, secret: str | bytes) -> str:
    """
    Descifra un string cifrado con encrypt_string.
    Si el texto no comienza con 'enc:v1:', se interpreta como texto heredado no cifrado
    y se devuelve tal cual (compatibilidad retroactiva transparente).
    """
    if not ciphertext:
        return ""
    if not isinstance(ciphertext, str):
        return str(ciphertext)

    if not ciphertext.startswith(PAYLOAD_PREFIX):
        return ciphertext

    b64_payload = ciphertext[len(PAYLOAD_PREFIX):]
    try:
        combined = base64.urlsafe_b64decode(b64_payload.encode("ascii"))
    except Exception as e:
        raise ValueError(f"Formato base64 de carga util invalido: {e}") from e

    if len(combined) < 12 + 16:  # Nonce (12) + GCM tag minimo (16)
        raise ValueError("Longitud de carga util cifrada insuficiente.")

    nonce = combined[:12]
    encrypted_data = combined[12:]

    key = derive_key(secret) if not (isinstance(secret, bytes) and len(secret) == 32) else secret
    aesgcm = AESGCM(key)

    try:
        decrypted_bytes = aesgcm.decrypt(nonce, encrypted_data, None)
        return decrypted_bytes.decode("utf-8")
    except Exception as e:
        raise ValueError(f"Fallo de autenticacion o clave incorrecta al descifrar: {e}") from e


def encrypt_dict_fields(data: dict[str, Any], fields: list[str], secret: str | bytes) -> dict[str, Any]:
    """Cifra en el diccionario unicamente las claves especificadas."""
    result = dict(data)
    for field in fields:
        if field in result and result[field] is not None:
            result[field] = encrypt_string(str(result[field]), secret)
    return result


def decrypt_dict_fields(data: dict[str, Any], fields: list[str], secret: str | bytes) -> dict[str, Any]:
    """Descifra en el diccionario unicamente las claves especificadas."""
    result = dict(data)
    for field in fields:
        if field in result and result[field] is not None:
            result[field] = decrypt_string(str(result[field]), secret)
    return result

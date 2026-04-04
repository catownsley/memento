"""
Encryption utilities for Memento.

Encrypts and decrypts local files that contain sensitive data,
such as the anonymizer mapping and allowlist. Uses Fernet symmetric
encryption with a key derived from a password via PBKDF2.

The encrypted files have a .enc extension. The plaintext versions
should be deleted after encryption and only exist in memory during use.
"""

import base64
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

SALT_SIZE = 16
KDF_ITERATIONS = 600_000  # NIST recommended minimum for PBKDF2-SHA256


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a Fernet key from a password and salt using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def encrypt_file(file_path: str, password: str) -> str:
    """
    Encrypt a file and write the ciphertext to file_path.enc.
    Returns the path to the encrypted file.

    The salt is prepended to the encrypted file so it can be
    read during decryption without storing it separately.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    salt = os.urandom(SALT_SIZE)
    key = _derive_key(password, salt)
    fernet = Fernet(key)

    with open(path, "rb") as f:
        plaintext = f.read()

    ciphertext = fernet.encrypt(plaintext)

    enc_path = str(path) + ".enc"
    with open(enc_path, "wb") as f:
        f.write(salt + ciphertext)

    return enc_path


def decrypt_file(enc_path: str, password: str) -> bytes:
    """
    Decrypt an encrypted file and return the plaintext bytes.
    Does not write the plaintext to disk.
    """
    path = Path(enc_path)
    if not path.exists():
        raise FileNotFoundError(f"Encrypted file not found: {enc_path}")

    with open(path, "rb") as f:
        data = f.read()

    salt = data[:SALT_SIZE]
    ciphertext = data[SALT_SIZE:]

    key = _derive_key(password, salt)
    fernet = Fernet(key)

    return fernet.decrypt(ciphertext)


def load_encrypted_json(enc_path: str, password: str) -> dict | list:  # type: ignore[type-arg]
    """
    Decrypt a .enc file and parse the plaintext as JSON.
    The plaintext only exists in memory, never written to disk.
    """
    plaintext = decrypt_file(enc_path, password)
    return json.loads(plaintext.decode("utf-8"))  # type: ignore[no-any-return]


def encrypt_mapping_files(password: str, mapping_path: str = "anonymizer_mapping.json", allowlist_path: str = "anonymizer_allowlist.json") -> None:
    """
    Encrypt the mapping and allowlist files, then delete the plaintext originals.
    """
    for file_path in [mapping_path, allowlist_path]:
        path = Path(file_path)
        if path.exists():
            enc_path = encrypt_file(file_path, password)
            path.unlink()
            print(f"Encrypted: {file_path} -> {enc_path}")
            print(f"Deleted plaintext: {file_path}")


def decrypt_mapping_files(password: str, mapping_path: str = "anonymizer_mapping.json", allowlist_path: str = "anonymizer_allowlist.json") -> tuple[dict[str, str], set[str]]:
    """
    Decrypt the mapping and allowlist files and return them in memory.
    Does not write plaintext to disk.
    """
    mapping: dict[str, str] = {}
    allowlist: set[str] = set()

    mapping_enc = mapping_path + ".enc"
    allowlist_enc = allowlist_path + ".enc"

    if Path(mapping_enc).exists():
        mapping = load_encrypted_json(mapping_enc, password)  # type: ignore[assignment]
    elif Path(mapping_path).exists():
        with open(mapping_path) as f:
            mapping = json.load(f)

    if Path(allowlist_enc).exists():
        allowlist = set(load_encrypted_json(allowlist_enc, password))  # type: ignore[arg-type]
    elif Path(allowlist_path).exists():
        with open(allowlist_path) as f:
            allowlist = set(json.load(f))

    return mapping, allowlist

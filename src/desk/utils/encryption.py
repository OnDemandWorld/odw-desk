"""
ODW.ai Desk — Field-Level Encryption Utility

AES-256-GCM encryption for PII fields and API keys.
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def derive_field_key(secret: str) -> bytes:
    """
    Single field-encryption key derivation (audit #47).

    Every encrypt/decrypt call site must use this so ciphertexts are portable
    between helpers. SHA-256 is retained for compatibility with already-stored
    ciphertexts; operators can set DESK_ENCRYPTION_KEY to separate the
    encryption key from the JWT signing secret.
    """
    import hashlib

    return hashlib.sha256(secret.encode()).digest()


def field_encryption_from_settings() -> "FieldEncryption":
    """FieldEncryption keyed by DESK_ENCRYPTION_KEY, falling back to SECRET_KEY."""
    from desk.config import get_settings

    settings = get_settings()
    return FieldEncryption(derive_field_key(settings.desk_encryption_key or settings.secret_key))


class FieldEncryption:
    """
    Field-level encryption using AES-256-GCM.

    Provides authenticated encryption for sensitive fields (PII, API keys).
    Each encryption generates a unique nonce for semantic security.
    """

    def __init__(self, key: bytes):
        """
        Initialize encryption with a 32-byte key.

        Args:
            key: 32-byte encryption key (AES-256)

        Raises:
            ValueError: If key is not 32 bytes
        """
        if len(key) != 32:
            raise ValueError(f"Encryption key must be 32 bytes, got {len(key)}")
        self.aesgcm = AESGCM(key)

    @classmethod
    def from_env(cls, env_var: str = "SECRET_KEY") -> "FieldEncryption":
        """
        Create encryption instance from environment variable.

        Args:
            env_var: Environment variable name containing the key

        Returns:
            FieldEncryption instance

        Raises:
            ValueError: If environment variable not set or key invalid
        """
        key_hex = os.environ.get(env_var)
        if not key_hex:
            raise ValueError(f"Environment variable {env_var} not set")

        # Audit #47: use the SAME derivation as every other call site — the
        # previous hex special-case produced ciphertexts that the admin/AI
        # paths (always SHA-256) could not decrypt, and vice versa.
        return cls(derive_field_key(key_hex))

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext string.

        Args:
            plaintext: String to encrypt

        Returns:
            Base64-encoded ciphertext with nonce (format: nonce:ciphertext)
        """
        nonce = os.urandom(12)  # 96-bit nonce for GCM
        ciphertext = self.aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

        # Combine nonce and ciphertext, encode as base64
        combined = nonce + ciphertext
        return base64.b64encode(combined).decode("ascii")

    def decrypt(self, ciphertext_b64: str) -> str:
        """
        Decrypt ciphertext string.

        Args:
            ciphertext_b64: Base64-encoded ciphertext (format: nonce:ciphertext)

        Returns:
            Decrypted plaintext string

        Raises:
            ValueError: If ciphertext is invalid or tampered
        """
        try:
            combined = base64.b64decode(ciphertext_b64.encode("ascii"))

            # Extract nonce (first 12 bytes) and ciphertext
            nonce = combined[:12]
            ciphertext = combined[12:]

            plaintext = self.aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode("utf-8")
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}") from e

    def encrypt_bytes(self, plaintext: bytes) -> str:
        """
        Encrypt bytes.

        Args:
            plaintext: Bytes to encrypt

        Returns:
            Base64-encoded ciphertext with nonce
        """
        nonce = os.urandom(12)
        ciphertext = self.aesgcm.encrypt(nonce, plaintext, None)

        combined = nonce + ciphertext
        return base64.b64encode(combined).decode("ascii")

    def decrypt_bytes(self, ciphertext_b64: str) -> bytes:
        """
        Decrypt to bytes.

        Args:
            ciphertext_b64: Base64-encoded ciphertext

        Returns:
            Decrypted bytes

        Raises:
            ValueError: If ciphertext is invalid or tampered
        """
        try:
            combined = base64.b64decode(ciphertext_b64.encode("ascii"))

            nonce = combined[:12]
            ciphertext = combined[12:]

            return self.aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}") from e


# Global encryption instance (lazy-loaded)
_encryption_instance: FieldEncryption | None = None


def get_encryption() -> FieldEncryption:
    """
    Get global encryption instance.

    Returns:
        FieldEncryption instance initialized from SECRET_KEY environment variable
    """
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = FieldEncryption.from_env()
    return _encryption_instance


def encrypt(plaintext: str) -> str:
    """Encrypt plaintext using global encryption instance."""
    return get_encryption().encrypt(plaintext)


def decrypt(ciphertext_b64: str) -> str:
    """Decrypt ciphertext using global encryption instance."""
    return get_encryption().decrypt(ciphertext_b64)


if __name__ == "__main__":
    # Test encryption
    import os

    os.environ["SECRET_KEY"] = "0" * 64  # 32 bytes in hex

    enc = FieldEncryption.from_env()

    # Test string encryption
    original = "Hello, World! This is a secret message with PII: +1234567890"
    encrypted = enc.encrypt(original)
    decrypted = enc.decrypt(encrypted)

    print(f"Original:  {original}")
    print(f"Encrypted: {encrypted[:50]}...")
    print(f"Decrypted: {decrypted}")
    print(f"Match: {original == decrypted}")

    # Test that different encryptions produce different ciphertexts (nonce)
    encrypted2 = enc.encrypt(original)
    print(f"\nDifferent ciphertexts: {encrypted != encrypted2}")

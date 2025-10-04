import os
import base64
import hashlib

# Try to use cryptography's Fernet if available; otherwise provide a
# minimal, deterministic fallback implementation for development/tests.
try:
    from cryptography.fernet import Fernet  # type: ignore
    _HAVE_FERNET = True
except Exception:
    Fernet = None  # type: ignore
    _HAVE_FERNET = False


def _get_fernet_key() -> bytes:
    # derive a 32-byte key from SECRETS_KEY or SECRET_KEY env var
    secret = os.getenv('SECRETS_KEY') or os.getenv('SECRET_KEY') or 'default-secret-key'
    h = hashlib.sha256(secret.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(h)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string. Uses Fernet when available; otherwise a
    simple reversible fallback that is safe for tests but NOT cryptographically
    secure. The fallback wraps the payload in a base64 token prefixed with
    'fallback:' so callers can detect it.
    """
    if _HAVE_FERNET and Fernet is not None:
        key = _get_fernet_key()
        f = Fernet(key)
        token = f.encrypt(plaintext.encode('utf-8'))
        return token.decode('utf-8')

    # Fallback: XOR with derived key bytes then base64 encode
    key_bytes = hashlib.sha256((os.getenv('SECRETS_KEY') or os.getenv('SECRET_KEY') or 'default-secret-key').encode('utf-8')).digest()
    pt_bytes = plaintext.encode('utf-8')
    out = bytearray()
    for i, b in enumerate(pt_bytes):
        out.append(b ^ key_bytes[i % len(key_bytes)])
    return 'fallback:' + base64.urlsafe_b64encode(bytes(out)).decode('utf-8')


def decrypt_value(token: str) -> str:
    """Decrypt a token produced by encrypt_value. Works with either Fernet
    tokens or the test fallback format.
    """
    if _HAVE_FERNET and Fernet is not None:
        key = _get_fernet_key()
        f = Fernet(key)
        return f.decrypt(token.encode('utf-8')).decode('utf-8')

    if token.startswith('fallback:'):
        b = token[len('fallback:'):]
        try:
            data = base64.urlsafe_b64decode(b.encode('utf-8'))
        except Exception:
            raise ValueError('Invalid token')
        key_bytes = hashlib.sha256((os.getenv('SECRETS_KEY') or os.getenv('SECRET_KEY') or 'default-secret-key').encode('utf-8')).digest()
        out = bytearray()
        for i, c in enumerate(data):
            out.append(c ^ key_bytes[i % len(key_bytes)])
        return bytes(out).decode('utf-8')

    raise ValueError('Fernet not available and token not in fallback format')

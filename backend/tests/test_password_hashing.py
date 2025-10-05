import pytest
from backend.app import hash_password, verify_password


def test_long_password_hash_and_verify():
    # Create a password longer than bcrypt's 72-byte limit when UTF-8 encoded
    pw = "p" * 100  # 100 characters -> 100 bytes in UTF-8
    hashed = hash_password(pw)
    assert isinstance(hashed, str)
    # Verification should succeed for the original password
    assert verify_password(pw, hashed) is True


def test_boundary_password_lengths():
    # Exactly 72 bytes should not be pre-hashed
    pw72 = "x" * 72
    hashed72 = hash_password(pw72)
    assert verify_password(pw72, hashed72) is True

    # 73 bytes should be pre-hashed (sha256 hex), but verification should still work
    pw73 = "x" * 73
    hashed73 = hash_password(pw73)
    assert verify_password(pw73, hashed73) is True


def test_bytes_and_non_utf8_bytes():
    # Bytes that are valid UTF-8
    bpw = b"password-bytes-\xc3\xa9"  # contains 'é'
    hashed = hash_password(bpw)
    assert verify_password(bpw, hashed) is True

    # Non-UTF8 bytes should be decoded with latin-1 fallback in the helper
    non_utf8 = bytes([0xff]) * 100
    hashed2 = hash_password(non_utf8)
    # Should still verify when passing the same raw bytes
    assert verify_password(non_utf8, hashed2) is True

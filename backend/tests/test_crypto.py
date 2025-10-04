import os
from backend.crypto import encrypt_value, decrypt_value


def test_encrypt_decrypt_roundtrip(monkeypatch):
    # set a deterministic secret key env var
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key')
    plaintext = 'super-secret-value-123'
    token = encrypt_value(plaintext)
    assert isinstance(token, str)
    recovered = decrypt_value(token)
    assert recovered == plaintext


def test_different_key_changes_cipher(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'key-one')
    token1 = encrypt_value('v')
    monkeypatch.setenv('SECRET_KEY', 'key-two')
    token2 = encrypt_value('v')
    # tokens should differ when key changes
    assert token1 != token2


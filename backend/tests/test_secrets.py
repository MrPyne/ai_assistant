def test_secret_encrypt_decrypt():
    from backend.crypto import encrypt_value, decrypt_value
    s = "supersecret"
    e = encrypt_value(s)
    d = decrypt_value(e)
    assert d == s

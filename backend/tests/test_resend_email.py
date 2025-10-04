import pytest
from unittest import mock

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_resend_email_existing_user_sends_email(monkeypatch):
    # register a user
    email = 'resendtest@example.com'
    password = 'pass'
    r = client.post('/api/auth/register', json={'email': email, 'password': password})
    assert r.status_code == 200

    sent = {}

    class DummySMTP:
        def __init__(self, host, port):
            sent['host'] = host
            sent['port'] = port

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def sendmail(self, from_addr, to_addrs, msg):
            sent['from'] = from_addr
            sent['to'] = to_addrs
            sent['msg'] = msg

    monkeypatch.setattr('smtplib.SMTP', DummySMTP)

    r2 = client.post('/api/auth/resend', json={'email': email})
    assert r2.status_code == 200
    data = r2.json()
    assert data.get('status') == 'ok'
    # assert SMTP was called
    assert sent.get('host') == 'localhost'
    assert sent.get('from') == 'noreply@example.com'
    assert sent.get('to') == [email]
    assert 'Resend' in sent.get('msg')


def test_resend_email_nonexistent_user_is_ok(monkeypatch):
    # Ensure calling resend for unknown email does not leak info and does not call SMTP
    email = 'doesnotexist@example.com'

    called = {'smtp': False}

    class DummySMTP2:
        def __init__(self, host, port):
            called['smtp'] = True

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def sendmail(self, from_addr, to_addrs, msg):
            called['smtp_send'] = True

    monkeypatch.setattr('smtplib.SMTP', DummySMTP2)

    r = client.post('/api/auth/resend', json={'email': email})
    assert r.status_code == 200
    data = r.json()
    assert data.get('status') == 'ok'
    # SMTP should not have been invoked because user doesn't exist
    assert called['smtp'] is False

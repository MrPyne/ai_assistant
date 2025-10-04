import pytest
from unittest import mock

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_resend_email_uses_smtp_patch():
    # register a user
    email = 'patchtest@example.com'
    password = 'pass'
    r = client.post('/api/auth/register', json={'email': email, 'password': password})
    assert r.status_code == 200

    # Patch the SMTP object where it's used in the app module
    with mock.patch('backend.app.smtplib.SMTP') as mock_smtp:
        # Configure the context manager returned by SMTP()
        smtp_instance = mock_smtp.return_value.__enter__.return_value
        smtp_instance.sendmail = mock.MagicMock()

        r2 = client.post('/api/auth/resend', json={'email': email})
        assert r2.status_code == 200
        data = r2.json()
        assert data.get('status') == 'ok'

        # Ensure SMTP was constructed with expected defaults
        mock_smtp.assert_called_with('localhost', 25)
        # Ensure sendmail was called and that the message contains our subject/body
        smtp_instance.sendmail.assert_called_once()
        called_args = smtp_instance.sendmail.call_args[0]
        assert called_args[0] == 'noreply@example.com'
        assert called_args[1] == [email]
        assert 'Resend' in called_args[2]

import os
from backend.adapters.openai_adapter import OpenAIAdapter
from backend.crypto import encrypt_value

class DummyProvider:
    def __init__(self, config=None, secret_id=None, workspace_id=1):
        self.config = config or {}
        self.secret_id = secret_id
        self.workspace_id = workspace_id


class DummyDB:
    def __init__(self, secrets):
        # secrets: dict id -> encrypted_value
        self._secrets = secrets

    def query(self, model):
        class Q:
            def __init__(self, secrets):
                self.secrets = secrets

            def filter(self, *args, **kwargs):
                # simplistic: assume filter contains Secret.id == value or Secret.name == value
                class F:
                    def __init__(self, secrets):
                        self.secrets = secrets

                    def first(self):
                        # return a simple object with encrypted_value attribute
                        # pick the first secret
                        for v in self.secrets.values():
                            return type('S', (), {'encrypted_value': v})()
                        return None

                return F(self.secrets)

        return Q(self._secrets)


def test_mock_mode_by_default(monkeypatch):
    # ensure live not enabled
    monkeypatch.delenv('LIVE_LLM', raising=False)
    monkeypatch.delenv('ENABLE_OPENAI', raising=False)
    provider = DummyProvider(config={'model': 'gpt-3.5-turbo'})
    adapter = OpenAIAdapter(provider)
    resp = adapter.generate('hello world')
    assert isinstance(resp, dict)
    assert resp.get('text', '').startswith('[mock]')


def test_resolves_inline_encrypted_key(monkeypatch):
    monkeypatch.setenv('LIVE_LLM', 'true')
    monkeypatch.setenv('SECRET_KEY', 'test-secret')
    # simulate provider with api_key_encrypted
    token = encrypt_value('sk-test-123')
    provider = DummyProvider(config={'api_key_encrypted': token})
    adapter = OpenAIAdapter(provider)
    # in live mode but network may fail; ensure _get_api_key returns decrypted key
    key = adapter._get_api_key()
    assert key == 'sk-test-123'
    # ensure we did not mutate provider config to include plaintext
    assert provider.config.get('api_key_encrypted') == token


def test_resolves_secret_reference(monkeypatch):
    monkeypatch.setenv('LIVE_LLM', 'true')
    monkeypatch.setenv('SECRET_KEY', 'test-secret')
    token = encrypt_value('sk-secret-ref')
    # provider has secret_id set; DB returns that secret
    provider = DummyProvider(config={}, secret_id=1)
    db = DummyDB({1: token})
    adapter = OpenAIAdapter(provider, db=db)
    key = adapter._get_api_key()
    assert key == 'sk-secret-ref'
    # ensure we did not write decrypted key back to provider or DB dummy store
    assert provider.config == {}

import os
from backend.adapters.ollama_adapter import OllamaAdapter
from backend.crypto import encrypt_value


class DummyProvider:
    def __init__(self, config=None, secret_id=None, workspace_id=1):
        self.config = config or {}
        self.secret_id = secret_id
        self.workspace_id = workspace_id


class DummyDB:
    def __init__(self, secrets):
        self._secrets = secrets

    def query(self, model):
        class Q:
            def __init__(self, secrets):
                self.secrets = secrets

            def filter(self, *args, **kwargs):
                class F:
                    def __init__(self, secrets):
                        self.secrets = secrets

                    def first(self):
                        for v in self.secrets.values():
                            return type('S', (), {'encrypted_value': v})()
                        return None

                return F(self.secrets)

        return Q(self._secrets)


def test_ollama_resolves_keys(monkeypatch):
    monkeypatch.setenv('LIVE_LLM', 'true')
    # opt-in to live LLMs for tests that exercise key resolution
    monkeypatch.setenv('ENABLE_LIVE_LLM', 'true')
    monkeypatch.setenv('SECRET_KEY', 'test-secret')
    token = encrypt_value('ollama-key-123')
    provider = DummyProvider(config={'api_key_encrypted': token})
    adapter = OllamaAdapter(provider)
    key = adapter._get_api_key()
    assert key == 'ollama-key-123'
    # ensure provider config was not mutated to include plaintext
    assert provider.config.get('api_key_encrypted') == token

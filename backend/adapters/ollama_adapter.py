import os
from typing import Any, Optional

from ..crypto import decrypt_value
import requests


class OllamaAdapter:
    """Ollama adapter.

    If ENABLE_OLLAMA env var is set to 'true', the adapter will make a real
    HTTP request to a running Ollama instance (default http://localhost:11434).
    Otherwise it returns a mocked response for safety in tests and CI.
    """

    def __init__(self, provider: Any, db=None):
        self.provider = provider
        self.db = db

    def _get_api_key(self) -> Optional[str]:
        cfg = (self.provider.config or {})
        # Prefer explicit secret_id reference on Provider
        if getattr(self.provider, "secret_id", None) and self.db:
            try:
                from ..models import Secret

                # Ensure secret is workspace-scoped
                s = (
                    self.db.query(Secret)
                    .filter(Secret.id == self.provider.secret_id, Secret.workspace_id == self.provider.workspace_id)
                    .first()
                )
                if s:
                    # Decrypt only for immediate use. Do not persist.
                    return decrypt_value(s.encrypted_value)
            except Exception:
                return None
        # Prefer encrypted inline key
        if cfg.get("api_key_encrypted"):
            try:
                return decrypt_value(cfg.get("api_key_encrypted"))
            except Exception:
                return None
        # Support secret reference (name of Secret stored in DB)
        secret_name = cfg.get("api_key_secret_name")
        if secret_name and self.db:
            try:
                from ..models import Secret

                s = (
                    self.db.query(Secret)
                    .filter(
                        Secret.name == secret_name,
                        Secret.workspace_id == self.provider.workspace_id,
                    )
                    .first()
                )
                if s:
                    return decrypt_value(s.encrypted_value)
            except Exception:
                return None
        return None

    def generate(self, prompt: str, **kwargs) -> dict:
        """Return a response dict.

        If ENABLE_LIVE_LLM or ENABLE_OLLAMA is true attempt to call the Ollama
        HTTP API. Provider config may supply 'host' and 'model'. Otherwise
        return a mocked response for safety in tests and CI.
        """
        api_key = self._get_api_key()
        enable_live = (
            os.getenv("ENABLE_LIVE_LLM", "false").lower() == "true"
            or os.getenv("ENABLE_OLLAMA", "false").lower() == "true"
        )

        model = (self.provider.config or {}).get("model") or "llama"

        if not enable_live:
            # Return a mock response that mirrors the real response shape so
            # downstream code (redaction, logging) behaves the same without
            # performing network IO.
            return {"text": f"[mock] OllamaAdapter would respond to prompt: {prompt[:100]}", "meta": {"model": model}}

        host = (self.provider.config or {}).get("host") or os.getenv("OLLAMA_HOST", "http://localhost:11434")

        payload = {"model": model, "prompt": prompt}
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            resp = requests.post(f"{host}/api/predict", json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            # Ollama may return different shapes; try common fields
            # data.get('result') or data.get('output') or join 'responses'
            if isinstance(data, dict):
                if "result" in data:
                    content = data.get("result")
                elif "output" in data:
                    content = data.get("output")
                else:
                    # fallback: stringify whole response
                    content = str(data)
            else:
                content = str(data)
            # Only return parsed content and minimal metadata to avoid
            # persisting provider-specific shapes that may include secrets.
            return {"text": content, "meta": {"model": model}}
        except Exception as e:
            return {"error": str(e)}

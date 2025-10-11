import os
from typing import Any, Optional

from ..crypto import decrypt_value
from ..llm_utils import is_live_llm_enabled
import requests


class OpenAIAdapter:
    """OpenAI adapter.

    By default the adapter returns a mocked response for safety in tests and CI.
    To enable real calls set LIVE_LLM='true' (recommended) or ENABLE_OPENAI='true'
    in the environment and ensure a valid API key is configured on the Provider
    (either api_key_encrypted or api_key_secret_name referring to a Secret).
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

                # Ensure the secret belongs to the same workspace as the provider
                s = (
                    self.db.query(Secret)
                    .filter(Secret.id == self.provider.secret_id, Secret.workspace_id == self.provider.workspace_id)
                    .first()
                )
                if s:
                    # Decrypt lazily and only return the API key to the caller
                    # (adapter). Callers must not persist this value. We avoid
                    # writing decrypted keys into logs or DB.
                    return decrypt_value(s.encrypted_value)
            except Exception:
                # Attempt a lightweight fallback for simple test DB objects that
                # expose a dict of secrets (tests use DummyDB with _secrets).
                try:
                    if hasattr(self.db, "_secrets") and getattr(self.provider, "secret_id", None) in self.db._secrets:
                        token = self.db._secrets[self.provider.secret_id]
                        return decrypt_value(token)
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
                # fallback to simple _secrets lookup by name if present
                try:
                    if hasattr(self.db, "_secrets"):
                        # DummyDB stores secrets by id only; skip
                        pass
                except Exception:
                    pass
                return None
        return None

    def _estimate_tokens(self, text: str) -> int:
        # Very rough tokenizer fallback used only when the OpenAI response does
        # not include usage information. This is intentionally conservative.
        if not text:
            return 0
        # estimate: average 0.75 words per token -> tokens ~= words / 0.75
        words = len(text.split())
        est = int(words / 0.75)
        return max(est, 1)

    def generate(self, prompt: str, **kwargs) -> dict:
        """Return a response dict.

        If LIVE_LLM or ENABLE_OPENAI env var is true and an API key is configured,
        make a real call to the Chat Completions endpoint. Otherwise return a
        mocked response for safety in tests/CI.
        """
        api_key = self._get_api_key()
        enable_live = is_live_llm_enabled("openai")

        if not enable_live or not api_key:
            # Mocked response for safety in CI/tests. Include a minimal meta
            # that matches the live adapter's shape so downstream redaction
            # and logging operate identically.
            return {
                "text": f"[mock] OpenAIAdapter would respond to prompt: {prompt[:100]}",
                "meta": {"usage": {"prompt_tokens": self._estimate_tokens(prompt), "completion_tokens": 0, "total_tokens": self._estimate_tokens(prompt)}, "model": (self.provider.config or {}).get("model", "gpt-3.5-turbo")},
            }

        model = (self.provider.config or {}).get("model", "gpt-3.5-turbo")

        # Build chat messages: simple single user message using the prompt
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 512),
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=20
            )
            resp.raise_for_status()
            data = resp.json()
            # Extract text from response
            choices = data.get("choices") or []
            if choices and isinstance(choices, list):
                # Grab assistant content(s)
                parts = []
                for c in choices:
                    # chat completion shape: {message: {role:..., content: ...}}
                    if isinstance(c, dict):
                        msg = c.get("message") or {}
                        content = msg.get("content") if isinstance(msg, dict) else None
                        if not content:
                            # older/alternate shape: c.get('text')
                            content = c.get("text")
                        if content:
                            parts.append(content)
                content = "\n".join(parts)
            else:
                content = ""

            # try to surface usage/cost info if available
            usage = data.get("usage") or {}
            if not usage:
                # estimate tokens conservatively
                usage = {
                    "prompt_tokens": self._estimate_tokens(prompt),
                    "completion_tokens": self._estimate_tokens(content),
                    "total_tokens": self._estimate_tokens(prompt) + self._estimate_tokens(content),
                }

            # Do not include the full raw provider response in the returned
            # meta to avoid accidental persistence of unexpected fields. Only
            # surface conservative usage information and model metadata.
            return {"text": content, "meta": {"usage": usage, "model": model}}
        except Exception as e:
            return {"error": str(e)}

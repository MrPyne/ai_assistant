import os
import logging
from typing import Any, Optional

from ..crypto import decrypt_value
from ..llm_utils import is_live_llm_enabled
import requests

logger = logging.getLogger(__name__)


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

        # Log provider high-level info to help debugging secret resolution.
        try:
            provider_id = getattr(self.provider, "id", None)
            provider_type = getattr(self.provider, "type", None)
            provider_workspace = getattr(self.provider, "workspace_id", None)
            has_secret_id = bool(getattr(self.provider, "secret_id", None))
            logger.debug(
                "OpenAIAdapter._get_api_key: provider_id=%s type=%s workspace=%s has_secret_id=%s config_keys=%s",
                provider_id,
                provider_type,
                provider_workspace,
                has_secret_id,
                list(cfg.keys()) if isinstance(cfg, dict) else None,
            )
        except Exception:
            logger.debug("OpenAIAdapter._get_api_key: failed to log provider metadata")

        # Prefer explicit secret_id reference on Provider
        if getattr(self.provider, "secret_id", None) and self.db:
            secret_id = getattr(self.provider, "secret_id", None)
            logger.debug("OpenAIAdapter: provider has secret_id=%s; attempting DB lookup", secret_id)
            try:
                from ..models import Secret

                # Ensure the secret belongs to the same workspace as the provider
                s = (
                    self.db.query(Secret)
                    .filter(Secret.id == self.provider.secret_id, Secret.workspace_id == self.provider.workspace_id)
                    .first()
                )
                if s:
                    logger.debug("OpenAIAdapter: found Secret row for id=%s (workspace=%s) created_at=%s", secret_id, getattr(s, 'workspace_id', None), getattr(s, 'created_at', None))
                    # Decrypt lazily and only return the API key to the caller
                    # (adapter). Callers must not persist this value. We avoid
                    # writing decrypted keys into logs or DB.
                    try:
                        val = decrypt_value(s.encrypted_value)
                        # Do not log the key itself; just indicate we resolved it
                        logger.debug("OpenAIAdapter: resolved api key from provider.secret_id (workspace=%s, provider=%s)", getattr(self.provider, 'workspace_id', None), getattr(self.provider, 'id', None))
                        return val
                    except Exception as e:
                        logger.debug("OpenAIAdapter: failed to decrypt provider secret_id=%s: %s", secret_id, e)
                        return None
                else:
                    logger.debug("OpenAIAdapter: no Secret row found for secret_id=%s (workspace=%s)", secret_id, getattr(self.provider, 'workspace_id', None))
            except Exception as e:
                logger.debug("OpenAIAdapter: exception while querying Secret by id=%s: %s", getattr(self.provider, 'secret_id', None), e)
                # Attempt a lightweight fallback for simple test DB objects that
                # expose a dict of secrets (tests use DummyDB with _secrets).
                try:
                    if hasattr(self.db, "_secrets") and getattr(self.provider, "secret_id", None) in self.db._secrets:
                        token = self.db._secrets[self.provider.secret_id]
                        logger.debug("OpenAIAdapter: found token in DummyDB._secrets for secret_id=%s", getattr(self.provider, 'secret_id', None))
                        try:
                            val = decrypt_value(token)
                            logger.debug("OpenAIAdapter: resolved api key from DummyDB._secrets for provider %s", getattr(self.provider, 'id', None))
                            return val
                        except Exception as e:
                            logger.debug("OpenAIAdapter: failed to decrypt DummyDB secret: %s", e)
                            return None
                except Exception as e2:
                    logger.debug("OpenAIAdapter: exception while accessing DummyDB._secrets: %s", e2)
                    return None
        # Prefer encrypted inline key
        if cfg.get("api_key_encrypted"):
            logger.debug("OpenAIAdapter: provider.config contains 'api_key_encrypted'; attempting to decrypt")
            try:
                val = decrypt_value(cfg.get("api_key_encrypted"))
                logger.debug("OpenAIAdapter: resolved api key from provider.config.api_key_encrypted for provider %s", getattr(self.provider, 'id', None))
                return val
            except Exception as e:
                logger.debug("OpenAIAdapter: failed to decrypt provider.config.api_key_encrypted: %s", e)
                return None
        # Support secret reference (name of Secret stored in DB)
        secret_name = cfg.get("api_key_secret_name")
        if secret_name and self.db:
            logger.debug("OpenAIAdapter: provider.config.api_key_secret_name=%s; attempting DB lookup by name", secret_name)
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
                    logger.debug("OpenAIAdapter: found Secret row for name='%s' (workspace=%s) id=%s created_at=%s", secret_name, getattr(s, 'workspace_id', None), getattr(s, 'id', None), getattr(s, 'created_at', None))
                    try:
                        val = decrypt_value(s.encrypted_value)
                        logger.debug("OpenAIAdapter: resolved api key from provider.config.api_key_secret_name='%s'", secret_name)
                        return val
                    except Exception as e:
                        logger.debug("OpenAIAdapter: failed to decrypt secret referenced by name '%s': %s", secret_name, e)
                        return None
                else:
                    logger.debug("OpenAIAdapter: no Secret row found for name='%s' (workspace=%s)", secret_name, getattr(self.provider, 'workspace_id', None))
            except Exception as e:
                logger.debug("OpenAIAdapter: exception while querying Secret by name='%s': %s", secret_name, e)
                # fallback to simple _secrets lookup by name if present
                try:
                    if hasattr(self.db, "_secrets"):
                        # DummyDB stores secrets by id only; skip
                        logger.debug("OpenAIAdapter: DummyDB._secrets present but lookup by name is not supported")
                except Exception as e2:
                    logger.debug("OpenAIAdapter: exception while accessing DummyDB._secrets: %s", e2)
                return None
        # Development / convenience: allow an explicit env var to supply an
        # OpenAI API key so quick local testing doesn't require creating a
        # Provider + Secret in the DB. This is intentionally last-resort and
        # only used when no provider-secret or inline-encrypted key is found.
        env_key = os.getenv("OPENAI_API_KEY")
        if env_key:
            # avoid logging the actual key value
            logger.debug("OpenAIAdapter: using OPENAI_API_KEY from environment (present=%s)", bool(env_key))
            return env_key

        logger.debug("OpenAIAdapter: no API key could be resolved from provider, config, or environment")
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
        logger.debug("OpenAIAdapter.generate: enable_live=%s api_key_present=%s provider_id=%s provider_type=%s", enable_live, bool(api_key), getattr(self.provider, 'id', None), getattr(self.provider, 'type', None))

        if not enable_live or not api_key:
            # Mocked response for safety in CI/tests. Include a minimal meta
            # that matches the live adapter's shape so downstream redaction
            # and logging operate identically.
            if not enable_live:
                logger.info("OpenAIAdapter: live LLM disabled via env; returning mock")
            else:
                logger.info("OpenAIAdapter: live LLM enabled but no API key found; returning mock")
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
            logger.debug("OpenAIAdapter: OpenAI API call succeeded status=%s model=%s", getattr(resp, 'status_code', None), model)
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
            logger.exception("OpenAIAdapter: exception while calling OpenAI API: %s", e)
            return {"error": str(e)}

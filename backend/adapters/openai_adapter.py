import os
import logging
from typing import Any, Optional

from ..crypto import decrypt_value
from ..llm_utils import is_live_llm_enabled
import requests

logger = logging.getLogger(__name__)

# Import-time sentinel so we can verify the running worker loaded this module
try:
    logger.warning("OpenAIAdapter MODULE LOADED marker=LLMLOG_v1 pid=%s", os.getpid())
except Exception:
    logger.warning("OpenAIAdapter MODULE LOADED marker=LLMLOG_v1")


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
        # Log construction so we can correlate provider objects with later
        # secret-resolution attempts.
        try:
            logger.warning(
                "OpenAIAdapter.__init__: provider_id=%s type=%s workspace=%s secret_id=%s db_present=%s",
                getattr(provider, "id", None),
                getattr(provider, "type", None),
                getattr(provider, "workspace_id", None),
                getattr(provider, "secret_id", None),
                bool(db),
            )
        except Exception:
            logger.warning("OpenAIAdapter.__init__: failed to log provider object")

    def _get_api_key(self) -> Optional[str]:
        cfg = (self.provider.config or {})

        # Very-visible diagnostic entry so we can tell whether the running
        # process is exercising this code path at all. We avoid logging any
        # secret material; this only records provider/DB presence.
        try:
            provider_id = getattr(self.provider, "id", None)
            provider_type = getattr(self.provider, "type", None)
            provider_workspace = getattr(self.provider, "workspace_id", None)
            has_secret_id = bool(getattr(self.provider, "secret_id", None))
            logger.warning(
                "OpenAIAdapter._get_api_key ENTRY: provider_id=%s type=%s workspace=%s has_secret_id=%s db_present=%s config_keys=%s",
                provider_id,
                provider_type,
                provider_workspace,
                has_secret_id,
                bool(self.db),
                list(cfg.keys()) if isinstance(cfg, dict) else None,
            )
        except Exception:
            logger.warning("OpenAIAdapter._get_api_key: failed to capture entry diagnostics")

        if not self.db:
            logger.info("OpenAIAdapter._get_api_key: no DB session provided; skipping DB-backed secret lookups")

        # Prefer explicit secret_id reference on Provider
        if getattr(self.provider, "secret_id", None) and self.db:
            secret_id = getattr(self.provider, "secret_id", None)
            logger.warning("OpenAIAdapter: provider has secret_id=%s; attempting DB lookup", secret_id)
            try:
                from ..models import Secret

                # Ensure the secret belongs to the same workspace as the provider
                s = (
                    self.db.query(Secret)
                    .filter(Secret.id == self.provider.secret_id, Secret.workspace_id == self.provider.workspace_id)
                    .first()
                )
                if s:
                    # Log non-sensitive metadata about the stored token so
                    # operators can determine whether the secret looks like a
                    # Fernet token or our fallback format without exposing the
                    # secret itself.
                    try:
                        token_len = len(getattr(s, 'encrypted_value', '') or '')
                        token_is_fallback = (getattr(s, 'encrypted_value', '') or '').startswith('fallback:')
                    except Exception:
                        token_len = None
                        token_is_fallback = None
                    logger.warning("OpenAIAdapter: found Secret row for id=%s (workspace=%s) created_at=%s token_len=%s token_is_fallback=%s", secret_id, getattr(s, 'workspace_id', None), getattr(s, 'created_at', None), token_len, token_is_fallback)
                    # Decrypt lazily and only return the API key to the caller
                    # (adapter). Callers must not persist this value. We avoid
                    # writing decrypted keys into logs or DB.
                    try:
                        val = decrypt_value(s.encrypted_value)
                        # Do not log the key itself; just indicate we resolved it
                        logger.warning("OpenAIAdapter: resolved api key from provider.secret_id (workspace=%s, provider=%s)", getattr(self.provider, 'workspace_id', None), getattr(self.provider, 'id', None))
                        return val
                    except Exception as e:
                        # Log the exception class and message but never log the
                        # secret material. This helps differentiate missing
                        # Fernet key vs malformed token.
                        logger.warning("OpenAIAdapter: failed to decrypt provider secret_id=%s: %s %s", secret_id, e.__class__.__name__, str(e))
                        return None
                else:
                    logger.warning("OpenAIAdapter: no Secret row found for secret_id=%s (workspace=%s)", secret_id, getattr(self.provider, 'workspace_id', None))
            except Exception as e:
                logger.warning("OpenAIAdapter: exception while querying Secret by id=%s: %s", getattr(self.provider, 'secret_id', None), e)
                # Attempt a lightweight fallback for simple test DB objects that
                # expose a dict of secrets (tests use DummyDB with _secrets).
                try:
                    if hasattr(self.db, "_secrets") and getattr(self.provider, "secret_id", None) in self.db._secrets:
                        token = self.db._secrets[self.provider.secret_id]
                        logger.warning("OpenAIAdapter: found token in DummyDB._secrets for secret_id=%s", getattr(self.provider, 'secret_id', None))
                        try:
                            val = decrypt_value(token)
                            logger.warning("OpenAIAdapter: resolved api key from DummyDB._secrets for provider %s", getattr(self.provider, 'id', None))
                            return val
                        except Exception as e:
                            logger.warning("OpenAIAdapter: failed to decrypt DummyDB secret: %s %s", e.__class__.__name__, str(e))
                            return None
                except Exception as e2:
                    logger.warning("OpenAIAdapter: exception while accessing DummyDB._secrets: %s", e2)
                    return None
        # Prefer encrypted inline key
        if cfg.get("api_key_encrypted"):
            logger.warning("OpenAIAdapter: provider.config contains 'api_key_encrypted'; attempting to decrypt")
            try:
                val = decrypt_value(cfg.get("api_key_encrypted"))
                logger.warning("OpenAIAdapter: resolved api key from provider.config.api_key_encrypted for provider %s", getattr(self.provider, 'id', None))
                return val
            except Exception as e:
                logger.warning("OpenAIAdapter: failed to decrypt provider.config.api_key_encrypted: %s", e)
                return None
        # Support secret reference (name of Secret stored in DB)
        secret_name = cfg.get("api_key_secret_name")
        if secret_name and self.db:
            logger.warning("OpenAIAdapter: provider.config.api_key_secret_name=%s; attempting DB lookup by name", secret_name)
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
                    logger.warning("OpenAIAdapter: found Secret row for name='%s' (workspace=%s) id=%s created_at=%s", secret_name, getattr(s, 'workspace_id', None), getattr(s, 'id', None), getattr(s, 'created_at', None))
                    try:
                        val = decrypt_value(s.encrypted_value)
                        logger.warning("OpenAIAdapter: resolved api key from provider.config.api_key_secret_name='%s'", secret_name)
                        return val
                    except Exception as e:
                        logger.warning("OpenAIAdapter: failed to decrypt secret referenced by name '%s': %s", secret_name, e)
                        return None
                else:
                    logger.warning("OpenAIAdapter: no Secret row found for name='%s' (workspace=%s)", secret_name, getattr(self.provider, 'workspace_id', None))
            except Exception as e:
                logger.warning("OpenAIAdapter: exception while querying Secret by name='%s': %s", secret_name, e)
                # fallback to simple _secrets lookup by name if present
                try:
                    if hasattr(self.db, "_secrets"):
                        # DummyDB stores secrets by id only; skip
                        logger.warning("OpenAIAdapter: DummyDB._secrets present but lookup by name is not supported")
                except Exception as e2:
                    logger.warning("OpenAIAdapter: exception while accessing DummyDB._secrets: %s", e2)
                return None
        # Development / convenience: allow an explicit env var to supply an
        # OpenAI API key so quick local testing doesn't require creating a
        # Provider + Secret in the DB. This is intentionally last-resort and
        # only used when no provider-secret or inline-encrypted key is found.
        env_key = os.getenv("OPENAI_API_KEY")
        if env_key:
            # avoid logging the actual key value
            logger.warning("OpenAIAdapter: using OPENAI_API_KEY from environment (present=%s)", bool(env_key))
            return env_key

        logger.warning("OpenAIAdapter: no API key could be resolved from provider, config, or environment")
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
        logger.warning("OpenAIAdapter.generate ENTRY: enable_live=%s api_key_present=%s provider_id=%s provider_type=%s db_present=%s secret_id=%s workspace=%s",
                       enable_live, bool(api_key), getattr(self.provider, 'id', None), getattr(self.provider, 'type', None), bool(self.db), getattr(self.provider, 'secret_id', None), getattr(self.provider, 'workspace_id', None))

        if not enable_live or not api_key:
            # Emit a high-visibility marker so operators can grep logs for the
            # exact failure path. This is safe because it does not include any
            # secret material.
            logger.error("OpenAIAdapter NO_API_KEY_MARKER: enable_live=%s api_key_present=%s provider_id=%s provider_type=%s secret_id=%s workspace=%s db_present=%s",
                         enable_live, bool(api_key), getattr(self.provider, 'id', None), getattr(self.provider, 'type', None), getattr(self.provider, 'secret_id', None), getattr(self.provider, 'workspace_id', None), bool(self.db))
            if not enable_live:
                logger.info("OpenAIAdapter: live LLM disabled via env; returning mock")
            else:
                logger.info("OpenAIAdapter: live LLM enabled but no API key found; returning mock")
            return {
                "text": f"[mock] OpenAIAdapter would respond to prompt: {prompt[:100]}",
                "meta": {"usage": {"prompt_tokens": self._estimate_tokens(prompt), "completion_tokens": 0, "total_tokens": self._estimate_tokens(prompt)}, "model": (self.provider.config or {}).get("model", "gpt-3.5-turbo")},
            }

        # Resolve model selection with priority:
        # 1. runtime override via kwargs['model']
        # 2. node-level preference passed in kwargs['node_model']
        # 3. provider.config['model']
        # 4. environment OPENAI_DEFAULT_MODEL
        # 5. built-in default
        runtime_model = kwargs.get('model')
        node_model = (kwargs.get('node_model') if kwargs.get('node_model') is not None else None)
        provider_model = (self.provider.config or {}).get('model')
        env_model = os.getenv('OPENAI_DEFAULT_MODEL')
        if runtime_model:
            model = runtime_model
            model_src = 'runtime'
        elif node_model:
            model = node_model
            model_src = 'node'
        elif provider_model:
            model = provider_model
            model_src = 'provider'
        elif env_model:
            model = env_model
            model_src = 'env'
        else:
            model = 'gpt-3.5-turbo'
            model_src = 'default'
        try:
            logger.info("OpenAIAdapter: selected model=%s source=%s provider_id=%s", model, model_src, getattr(self.provider, 'id', None))
        except Exception:
            pass

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
            logger.info("OpenAIAdapter: OpenAI API call succeeded status=%s model=%s", getattr(resp, 'status_code', None), model)
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

def redact_secrets(obj):
    """Recursively redact secret-like keys in dicts and items in lists or strings.

    Behaviour:
    - For dicts: any key whose lowercase form appears in the SKIP_KEYS set is
      replaced with the literal string "[REDACTED]" (preserves key name).
    - For lists: recurse into items.
    - For strings: apply a set of conservative regexes to remove common token
      formats (OpenAI keys, AWS keys, JWTs, PEM blocks, long base64/hex blobs,
      Google API keys, SAS signatures, query param tokens, etc.).

    This function is intentionally conservative to avoid accidental data
    corruption; add patterns carefully and expand tests when adding new
    providers.
    """
    import re

    SKIP_KEYS = {
        # common secret-containing keys
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "authorization_header",
        "auth",
        "private_key",
        "private_key_id",
        "client_secret",
        "client_id",
        "access_token",
        "refresh_token",
        "secret_access_key",
        "access_key",
        "sig",
        "signature",
        "credential",
        "credentials",
        "service_account",
        "privatekey",
    }

    def _redact_str(s: str) -> str:
        # apply a sequence of regex substitutions. Order matters for some
        # overlapping patterns; prefer specific vendor patterns first.

        # OpenAI-style keys: sk-<...>
        s = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", s)

        # Google OAuth2/ya29 tokens
        s = re.sub(r"ya29\.[A-Za-z0-9_\-\.]{8,}", "[REDACTED]", s)

        # Google API keys (AIza...)
        s = re.sub(r"AIza[0-9A-Za-z\-_]{35,}", "[REDACTED]", s)

        # Bearer tokens (case-insensitive)
        s = re.sub(r"(?i)bearer\s+[A-Za-z0-9\._\-\=]{8,}", "[REDACTED]", s)

        # Generic token= or access_token= patterns. Keep the left-hand name and
        # replace the value with [REDACTED] (avoid swallowing surrounding text).
        s = re.sub(r"(?i)(access_token|token)=([A-Za-z0-9_\-\.]{8,})", lambda m: f"{m.group(1)}=[REDACTED]", s)

        # Other common token parameter names (id_token, oauth_token, refresh_token)
        s = re.sub(r"(?i)(id_token|oauth_token|refresh_token)=([A-Za-z0-9_\-\. %]{8,})", lambda m: f"{m.group(1)}=[REDACTED]", s)

        # key=... patterns (e.g., ?key=XYZ)
        s = re.sub(r"(?i)key=([A-Za-z0-9_\-\.]{8,})", "key=[REDACTED]", s)

        # AWS Access Key IDs (AKIA...)
        s = re.sub(r"AKIA[0-9A-Z]{16}", "[REDACTED]", s)

        # AWS Secret Access Key or other long base64-like secrets (conservative)
        s = re.sub(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40,}(?![A-Za-z0-9/+=])", "[REDACTED]", s)

        # PEM private keys (RSA/PRIVATE KEY blocks)
        s = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----", "[REDACTED]", s)
        s = re.sub(r"-----BEGIN RSA PRIVATE KEY-----[\s\S]+?-----END RSA PRIVATE KEY-----", "[REDACTED]", s)
        # Additional PEM variants (OPENSSH, EC)
        s = re.sub(r"-----BEGIN OPENSSH PRIVATE KEY-----[\s\S]+?-----END OPENSSH PRIVATE KEY-----", "[REDACTED]", s)
        s = re.sub(r"-----BEGIN EC PRIVATE KEY-----[\s\S]+?-----END EC PRIVATE KEY-----", "[REDACTED]", s)

        # SSH key blobs
        s = re.sub(r"ssh-(rsa|ed25519) [A-Za-z0-9+/=\.]{40,}", "[REDACTED]", s)

        # Azure SAS signature 'sig=' or combined 'se=...&sig=...'
        s = re.sub(r"(?i)sig=([A-Za-z0-9%_\-\.]{16,})", "sig=[REDACTED]", s)
        s = re.sub(r"(?i)se=[0-9TZ:\-\.]+&?sig=[A-Za-z0-9%_\-\.]{8,}", "se=[REDACTED]&sig=[REDACTED]", s)
        # URL-encoded variants of sig/se (e.g., sig%3D...)
        s = re.sub(r"(?i)sig%3D([A-Za-z0-9%_\-\.]{8,})", "sig%3D[REDACTED]", s)
        s = re.sub(r"(?i)se%3D[0-9TZ%:\-\.]+%26?sig%3D[A-Za-z0-9%_\-\.]{8,}", "se%3D[REDACTED]%26sig%3D[REDACTED]", s)

        # JWT-like tokens: usually three dot-separated base64url parts and often
        # start with 'eyJ' for JSON web tokens
        s = re.sub(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", "[REDACTED]", s)

        # Generic long hex strings (40+ hex chars)
        s = re.sub(r"(?<![0-9a-fA-F])[0-9a-fA-F]{40,}(?![0-9a-fA-F])", "[REDACTED]", s)

        # Google service account JSON sometimes is embedded as a string containing
        # a private_key field; redact the entire PEM inside JSON strings.
        s = re.sub(r'"private_key"\s*:\s*"-----BEGIN [^\"]+-----[\s\S]+?-----END [^\"]+-----"', '"private_key":"[REDACTED]"', s)

        # private_key_id fields in service account JSON (hex-like)
        s = re.sub(r'"private_key_id"\s*:\s*"[0-9a-fA-F]{16,}"', '"private_key_id":"[REDACTED]"', s)

        return s

    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = k.lower() if isinstance(k, str) else k
            if isinstance(kl, str) and kl in SKIP_KEYS:
                out[k] = "[REDACTED]"
            else:
                out[k] = redact_secrets(v)
        return out

    if isinstance(obj, list):
        return [redact_secrets(v) for v in obj]

    if isinstance(obj, str):
        return _redact_str(obj)

    # leave other types untouched
    return obj

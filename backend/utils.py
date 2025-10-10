def redact_secrets(obj):
    """Recursively redact secret-like keys in dicts and items in lists."""
    import re

    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = k.lower()
            # include authorization header and common secret-like keys
            # Extend common names that often contain secrets so keys like
            # 'private_key', 'client_secret', 'access_token' are redacted.
            if kl in (
                "password",
                "secret",
                "token",
                "api_key",
                "apikey",
                "authorization",
                "private_key",
                "client_secret",
                "access_token",
                "refresh_token",
                "sig",
            ):
                out[k] = "[REDACTED]"
            else:
                out[k] = redact_secrets(v)
        return out
    if isinstance(obj, list):
        return [redact_secrets(v) for v in obj]
    # redact obvious API key patterns in strings
    if isinstance(obj, str):
        # common OpenAI key pattern starts with sk-
        obj = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", obj)
        # Bearer tokens or key=... patterns
        obj = re.sub(r"(?i)bearer\s+[A-Za-z0-9\._\-\=]{8,}", "[REDACTED]", obj)
        obj = re.sub(r"key=([A-Za-z0-9\._\-]{8,})", "key=[REDACTED]", obj)
        # Google OAuth2 access tokens often start with ya29.
        obj = re.sub(r"ya29\.[A-Za-z0-9_\-\.]{8,}", "[REDACTED]", obj)
        # common 'token=' or 'access_token=' query-like params
        obj = re.sub(r"(?i)(?:access_token|token)=([A-Za-z0-9_\-\.]{8,})", "\1=[REDACTED]", obj)
        # AWS Access Key IDs (e.g. AKIAxxxxxxxxxxxxxx)
        obj = re.sub(r"AKIA[0-9A-Z]{16}", "[REDACTED]", obj)
        # AWS Secret Access Keys or other long base64-like secrets (conservative: 40+ chars)
        obj = re.sub(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40,}(?![A-Za-z0-9/+=])", "[REDACTED]", obj)
        # Google API keys (common format starts with AIza)
        obj = re.sub(r"AIza[0-9A-Za-z\-_]{35,}", "[REDACTED]", obj)
        # JWTs typically start with eyJ and have three dot-separated base64url parts
        obj = re.sub(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", "[REDACTED]", obj)
        # PEM private keys (RSA/PRIVATE KEY blocks)
        obj = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----", "[REDACTED]", obj)
        # SSH public/private key blobs (e.g., ssh-rsa AAAA...)
        obj = re.sub(r"ssh-(rsa|ed25519) [A-Za-z0-9+/=\.]{40,}", "[REDACTED]", obj)
        # Azure SAS signature parameter 'sig=' or SharedAccessSignature-like tokens
        obj = re.sub(r"(?i)sig=([A-Za-z0-9%_\-\.]{16,})", "sig=[REDACTED]", obj)
        # Azure SAS tokens often include 'se=' (expiry) and 'sig=' together; redact common SAS-like blobs
        obj = re.sub(r"(?i)se=[0-9TZ:\-\.]+&?sig=[A-Za-z0-9%_\-\.]{8,}", "se=[REDACTED]&sig=[REDACTED]", obj)
        # Generic long hex strings (40+ hex chars) often correspond to SHA-like digests
        obj = re.sub(r"(?<![0-9a-fA-F])[0-9a-fA-F]{40,}(?![0-9a-fA-F])", "[REDACTED]", obj)
        return obj
    return obj

def redact_secrets(obj):
    """Recursively redact secret-like keys in dicts and items in lists."""
    import re

    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = k.lower()
            # include authorization header and common secret-like keys
            if kl in ("password", "secret", "token", "api_key", "apikey", "authorization"):
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
        # AWS Access Key IDs (e.g. AKIAxxxxxxxxxxxxxx)
        obj = re.sub(r"AKIA[0-9A-Z]{16}", "[REDACTED]", obj)
        return obj
    return obj

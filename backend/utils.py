"""Utilities for redacting secret-like content from structures.

Primary entrypoint: redact_secrets(obj)

This module also exposes simple in-process telemetry useful for tuning
redaction heuristics in tests/CI. The telemetry is intentionally minimal
and can be disabled or reset via the helper functions below.
"""

import re
import os
import threading

# Simple in-memory telemetry counters. Tests/CI can call
# get_redaction_metrics() / reset_redaction_metrics() to observe activity.
_REDACTION_METRICS = {
    'count': 0,  # total number of string redactions performed
    'patterns': {},  # map pattern name -> total replacements
}
_METRICS_LOCK = threading.Lock()

# Cache compiled vendor regexes to avoid reparsing on every redact call.
# We track the raw env values so tests/long-running processes that change
# the env can trigger a reload.
_VENDOR_LOCK = threading.Lock()
_COMPILED_VENDOR_REGEXES = None
_VENDOR_REGEXES_RAW = None

# Safety limits for user-provided vendor regexes. These are intentionally
# conservative to avoid DoS by extremely large lists or very long patterns.
_MAX_VENDOR_REGEXES = 50
_MAX_VENDOR_PATTERN_LENGTH = 1000


def get_redaction_metrics():
    """Return a shallow copy of current redaction metrics."""
    with _METRICS_LOCK:
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in _REDACTION_METRICS.items()}


def reset_redaction_metrics():
    """Reset in-memory redaction metrics to zero."""
    with _METRICS_LOCK:
        _REDACTION_METRICS['count'] = 0
        _REDACTION_METRICS['patterns'].clear()


def _note_redaction(pattern_name: str, n: int = 1):
    if n <= 0:
        return
    with _METRICS_LOCK:
        _REDACTION_METRICS['count'] += n
        _REDACTION_METRICS['patterns'][pattern_name] = _REDACTION_METRICS['patterns'].get(pattern_name, 0) + n


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
        # We'll apply each substitution via re.subn so we can record simple
        # telemetry about which pattern matched and how many replacements
        # occurred. The order below mirrors the previous implementation.

        def _apply(pat, repl, name, flags=0):
            try:
                new, n = re.subn(pat, repl, s, flags=flags)
            except TypeError:
                # Some repls may be callables that expect a match object; try
                # re.subn with the callable directly.
                new, n = re.subn(pat, repl, s, flags=flags)
            if n:
                _note_redaction(name, n)
            return new

        # OpenAI-style keys: sk-<...>
        s = _apply(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", 'openai_sk')

        # Google OAuth2/ya29 tokens
        s = _apply(r"ya29\.[A-Za-z0-9_\-\.]{8,}", "[REDACTED]", 'google_ya29')

        # Google API keys (AIza...)
        s = _apply(r"AIza[0-9A-Za-z\-_]{35,}", "[REDACTED]", 'google_api_key')

        # Bearer tokens (case-insensitive)
        s = _apply(r"bearer\s+[A-Za-z0-9\._\-\=]{8,}", "[REDACTED]", 'bearer_token', flags=re.I)

        # Generic token= or access_token= patterns. Keep the left-hand name and
        # replace the value with [REDACTED] (avoid swallowing surrounding text).
        s = _apply(r"(access_token|token)=([A-Za-z0-9_\-\.]{8,})", lambda m: f"{m.group(1)}=[REDACTED]", 'token_param', flags=re.I)

        # Other common token parameter names (id_token, oauth_token, refresh_token)
        s = _apply(r"(id_token|oauth_token|refresh_token)=([A-Za-z0-9_\-\. %]{8,})", lambda m: f"{m.group(1)}=[REDACTED]", 'other_token_params', flags=re.I)

        # key=... patterns (e.g., ?key=XYZ)
        s = _apply(r"key=([A-Za-z0-9_\-\.]{8,})", "key=[REDACTED]", 'key_param', flags=re.I)

        # AWS Access Key IDs (AKIA...)
        s = _apply(r"AKIA[0-9A-Z]{16}", "[REDACTED]", 'aws_akid')

        # AWS Secret Access Key or other long base64-like secrets (conservative)
        s = _apply(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40,}(?![A-Za-z0-9/+=])", "[REDACTED]", 'long_base64')

        # PEM private keys (RSA/PRIVATE KEY blocks)
        s = _apply(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----", "[REDACTED]", 'pem_private')
        s = _apply(r"-----BEGIN RSA PRIVATE KEY-----[\s\S]+?-----END RSA PRIVATE KEY-----", "[REDACTED]", 'pem_rsa')
        # Additional PEM variants (OPENSSH, EC)
        s = _apply(r"-----BEGIN OPENSSH PRIVATE KEY-----[\s\S]+?-----END OPENSSH PRIVATE KEY-----", "[REDACTED]", 'pem_openssh')
        s = _apply(r"-----BEGIN EC PRIVATE KEY-----[\s\S]+?-----END EC PRIVATE KEY-----", "[REDACTED]", 'pem_ec')

        # SSH key blobs
        s = _apply(r"ssh-(rsa|ed25519) [A-Za-z0-9+/=\.]{40,}", "[REDACTED]", 'ssh_blob')

        # Azure SAS signature 'sig=' or combined 'se=...&sig=...'
        s = _apply(r"sig=([A-Za-z0-9%_\-\.]{16,})", "sig=[REDACTED]", 'azure_sig', flags=re.I)
        s = _apply(r"se=[0-9TZ:\-\.]+&?sig=[A-Za-z0-9%_\-\.]{8,}", "se=[REDACTED]&sig=[REDACTED]", 'azure_se_sig', flags=re.I)
        # URL-encoded variants of sig/se (e.g., sig%3D...)
        s = _apply(r"sig%3D([A-Za-z0-9%_\-\.]{8,})", "sig%3D[REDACTED]", 'azure_sig_encoded', flags=re.I)
        s = _apply(r"se%3D[0-9TZ%:\-\.]+%26?sig%3D[A-Za-z0-9%_\-\.]{8,}", "se%3D[REDACTED]%26sig%3D[REDACTED]", 'azure_se_sig_encoded', flags=re.I)

        # JWT-like tokens: usually three dot-separated base64url parts and often
        # start with 'eyJ' for JSON web tokens
        s = _apply(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", "[REDACTED]", 'jwt')

        # Generic long hex strings (40+ hex chars)
        s = _apply(r"(?<![0-9a-fA-F])[0-9a-fA-F]{40,}(?![0-9a-fA-F])", "[REDACTED]", 'long_hex')

        # Google service account JSON sometimes is embedded as a string containing
        # a private_key field; redact the entire PEM inside JSON strings.
        s = _apply(r'"private_key"\s*:\s*"-----BEGIN [^\"]+-----[\s\S]+?-----END [^\"]+-----"', '"private_key":"[REDACTED]"', 'sa_private_key')

        # private_key_id fields in service account JSON (hex-like)
        s = _apply(r'"private_key_id"\s*:\s*"[0-9a-fA-F]{16,}"', '"private_key_id":"[REDACTED]"', 'sa_private_key_id')

        # Optionally include additional vendor-specific patterns. This is
        # guarded by the REDACT_VENDOR_PATTERNS environment variable so
        # callers can opt-in to broader heuristics that may increase false
        # positives.
        vendor_enabled = os.getenv('REDACT_VENDOR_PATTERNS', '').lower() in ('1', 'true', 'yes')
        if vendor_enabled:
            # GitHub personal access tokens (newer 'ghp_' format)
            s = _apply(r"ghp_[A-Za-z0-9_]{36,}", "[REDACTED]", 'github_ghp')
            # Slack tokens (xoxp-, xoxb-)
            s = _apply(r"xox[pbo]-[A-Za-z0-9-]{8,}", "[REDACTED]", 'slack_xox')
            # Generic vendor API keys prefixed with known labels (conservative length)
            s = _apply(r"(sk_live|sk_test)_[A-Za-z0-9]{8,}", "[REDACTED]", 'stripe_sk', flags=re.I)

        # Allow callers to inject additional redaction regexes at runtime via
        # the REDACT_VENDOR_REGEXES environment variable. To avoid reparsing
        # and recompiling on every redact call we cache compiled regexes and
        # only reload when the raw env value changes. We also enforce a few
        # conservative safety limits to avoid resource exhaustion from
        # untrusted input.
        extra = os.getenv('REDACT_VENDOR_REGEXES', '')
        try:
            global _COMPILED_VENDOR_REGEXES, _VENDOR_REGEXES_RAW
            with _VENDOR_LOCK:
                if _VENDOR_REGEXES_RAW != extra:
                    compiled = []
                    raw = extra or ''
                    if raw.strip():
                        try:
                            import json as _json

                            if raw.strip().startswith('['):
                                parsed = _json.loads(raw)
                                for item in parsed:
                                    if len(compiled) >= _MAX_VENDOR_REGEXES:
                                        break
                                    if isinstance(item, dict) and 'pattern' in item:
                                        pat = item.get('pattern') or ''
                                        if not pat or len(pat) > _MAX_VENDOR_PATTERN_LENGTH:
                                            continue
                                        pname = item.get('name') or f"extra_{abs(hash(pat))}"
                                        try:
                                            cre = re.compile(pat)
                                            compiled.append((pname, cre))
                                        except Exception:
                                            # skip invalid patterns
                                            continue
                            else:
                                # newline-separated name:pattern entries
                                for line in raw.splitlines():
                                    if len(compiled) >= _MAX_VENDOR_REGEXES:
                                        break
                                    line = line.strip()
                                    if not line or line.startswith('#'):
                                        continue
                                    if ':' in line:
                                        name, pat = line.split(':', 1)
                                        name = name.strip() or f"extra_{abs(hash(pat))}"
                                        pat = pat.strip()
                                        if not pat or len(pat) > _MAX_VENDOR_PATTERN_LENGTH:
                                            continue
                                        try:
                                            cre = re.compile(pat)
                                            compiled.append((name, cre))
                                        except Exception:
                                            continue
                        except Exception:
                            compiled = []

                    _COMPILED_VENDOR_REGEXES = compiled
                    _VENDOR_REGEXES_RAW = extra

            # apply compiled patterns
            if _COMPILED_VENDOR_REGEXES:
                for pname, cre in _COMPILED_VENDOR_REGEXES:
                    try:
                        s = _apply(cre, "[REDACTED]", pname)
                    except Exception:
                        continue
        except Exception:
            # ignore malformed config; do not raise
            pass

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

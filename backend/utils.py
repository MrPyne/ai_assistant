"""Utilities for redacting secret-like content from structures.

Primary entrypoint: redact_secrets(obj)

This module also exposes simple in-process telemetry useful for tuning
redaction heuristics in tests/CI. The telemetry is intentionally minimal
and can be disabled or reset via the helper functions below.
"""

import re
import os
import threading
import multiprocessing
import time

# Optional faster/safer regex engine with timeout support. If available we
# will compile vendor-provided patterns with the 'regex' package and apply a
# short timeout when running them to avoid pathological backtracking DoS.
try:
    import regex as _regex  # type: ignore
    _REGEX_AVAILABLE = True
except Exception:
    _regex = None
    _REGEX_AVAILABLE = False

# Note: timeout is read dynamically at time of application so tests or
# long-running processes can adjust REDACT_VENDOR_REGEX_TIMEOUT_MS at
# runtime without needing to reload the module. Value is interpreted as
# milliseconds and converted to seconds when passed to the regex engine.

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
        # Return a shallow copy so callers can't mutate the in-process
        # counters directly. Dict-valued entries are copied to preserve
        # snapshot semantics for tests/telemetry readers.
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in _REDACTION_METRICS.items()}


def reset_redaction_metrics():
    """Reset in-memory redaction metrics to zero."""
    with _METRICS_LOCK:
        _REDACTION_METRICS['count'] = 0
        _REDACTION_METRICS['patterns'].clear()
        # Clear vendor-specific diagnostic counters if present
        _REDACTION_METRICS.setdefault('vendor_timeouts', {}).clear()
        _REDACTION_METRICS.setdefault('vendor_errors', {}).clear()
        _REDACTION_METRICS.setdefault('vendor_budget_exceeded', {}).clear()


def _note_redaction(pattern_name: str, n: int = 1):
    if n <= 0:
        return
    with _METRICS_LOCK:
        _REDACTION_METRICS['count'] += n
        _REDACTION_METRICS['patterns'][pattern_name] = _REDACTION_METRICS['patterns'].get(pattern_name, 0) + n


def _note_vendor_timeout(pattern_name: str, n: int = 1):
    """Record that applying a vendor regex timed out/skipped.

    This helps tests and telemetry distinguish between patterns that
    successfully matched and patterns that were skipped due to the
    configured timeout.
    """
    if n <= 0:
        return
    with _METRICS_LOCK:
        d = _REDACTION_METRICS.setdefault('vendor_timeouts', {})
        d[pattern_name] = d.get(pattern_name, 0) + n


def _note_vendor_error(pattern_name: str, n: int = 1):
    """Record a non-timeout error related to a vendor pattern (e.g. compile error).

    These are non-fatal and the implementation preserves the previous
    behavior of silently skipping malformed patterns; recording the
    occurrence makes debugging easier in CI or telemetry.
    """
    if n <= 0:
        return
    with _METRICS_LOCK:
        d = _REDACTION_METRICS.setdefault('vendor_errors', {})
        d[pattern_name] = d.get(pattern_name, 0) + n


def _note_vendor_budget_exceeded(key: str = 'aggregate', n: int = 1):
    """Record that an aggregate vendor regex time budget was exceeded.

    This is recorded separately from per-pattern timeouts so CI and
    telemetry can distinguish between a single pathological pattern and
    the cumulative cost of applying many vendor patterns.
    """
    if n <= 0:
        return
    with _METRICS_LOCK:
        d = _REDACTION_METRICS.setdefault('vendor_budget_exceeded', {})
        d[key] = d.get(key, 0) + n


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
                                            if _REGEX_AVAILABLE:
                                                cre = _regex.compile(pat)
                                                compiled.append((pname, cre, 'regex', pat))
                                            else:
                                                cre = re.compile(pat)
                                                compiled.append((pname, cre, 're', pat))
                                        except Exception:
                                            # skip invalid patterns but record the
                                            # occurrence for telemetry to aid CI
                                            _note_vendor_error(pname)
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
                                            if _REGEX_AVAILABLE:
                                                cre = _regex.compile(pat)
                                                compiled.append((name, cre, 'regex', pat))
                                            else:
                                                cre = re.compile(pat)
                                                compiled.append((name, cre, 're', pat))
                                        except Exception:
                                            _note_vendor_error(name)
                                            continue
                        except Exception:
                            compiled = []

                    _COMPILED_VENDOR_REGEXES = compiled
                    _VENDOR_REGEXES_RAW = extra

        # apply compiled patterns
                    if _COMPILED_VENDOR_REGEXES:
                        # enforce an aggregate time budget for applying all
                        # vendor regexes to avoid repeated small costs adding
                        # up to a DoS. This budget is checked before each
                        # pattern application so tests can force an immediate
                        # skip by setting the budget to 0.
                        try:
                            total_budget_ms = int(os.getenv('REDACT_VENDOR_REGEX_TOTAL_TIMEOUT_MS', '200'))
                        except Exception:
                            total_budget_ms = 200
                        start_time = time.time()
                        for pname, cre, engine, _raw in _COMPILED_VENDOR_REGEXES:
                            # check aggregate budget before attempting this pattern
                            elapsed_ms = (time.time() - start_time) * 1000.0
                            if elapsed_ms >= total_budget_ms:
                                _note_vendor_budget_exceeded()
                                break
                            try:
                                # Use the compiled pattern's subn method. If the
                                # 'regex' package is available we apply a short
                                # timeout to avoid pathological backtracking
                                # patterns. We treat timeout exceptions and
                                # other exceptions as non-fatal skips for that
                                # pattern but record telemetry so CI/ops can
                                # surface problematic patterns.
                                if engine == 'regex' and _REGEX_AVAILABLE:
                                    # Read the timeout dynamically in case tests
                                    # or runtime adjust the env var.
                                    try:
                                        timeout_ms = int(os.getenv('REDACT_VENDOR_REGEX_TIMEOUT_MS', '100'))
                                    except Exception:
                                        timeout_ms = 100
                                    # regex.subn expects timeout in seconds (float)
                                    new, n = cre.subn("[REDACTED]", s, timeout=timeout_ms / 1000.0)
                                else:
                                    new, n = cre.subn("[REDACTED]", s)
                                if n:
                                    _note_redaction(pname, n)
                                    s = new
                            except Exception as e:
                                # regex raises a specific TimeoutError type on
                                # timeouts; when that happens record a vendor
                                # timeout metric. Other exceptions are recorded
                                # as vendor errors and skipped silently to
                                # preserve backward compatibility.
                                try:
                                    if _REGEX_AVAILABLE and isinstance(e, _regex.TimeoutError):
                                        _note_vendor_timeout(pname)
                                        continue
                                except Exception:
                                    # defensive: if _regex.TimeoutError isn't
                                    # available for some reason, fall through.
                                    pass
                                _note_vendor_error(pname)
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

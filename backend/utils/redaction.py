"""Redaction logic extracted from utils.py.

This module focuses on the string/dict/list redaction functionality and
keeps vendor regex handling and telemetry hooks. It imports the telemetry
helpers from the metrics module to report counts.
"""
import re
import os
import time
try:
    import regex as _regex  # type: ignore
    _REGEX_AVAILABLE = True
except Exception:
    _regex = None
    _REGEX_AVAILABLE = False

from .metrics import _note_redaction, _note_vendor_timeout, _note_vendor_error, _note_vendor_budget_exceeded

# Cache compiled vendor regexes to avoid reparsing on every redact call.
_VENDOR_LOCK = threading = None
try:
    import threading as _threading
    _VENDOR_LOCK = _threading.Lock()
except Exception:
    _VENDOR_LOCK = None

_COMPILED_VENDOR_REGEXES = None
_VENDOR_REGEXES_RAW = None

# Safety limits
_MAX_VENDOR_REGEXES = 50
_MAX_VENDOR_PATTERN_LENGTH = 1000


def redact_secrets(obj):
    SKIP_KEYS = {
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
        def _apply(pat, repl, name, flags=0):
            try:
                new, n = re.subn(pat, repl, s, flags=flags)
            except TypeError:
                new, n = re.subn(pat, repl, s, flags=flags)
            if n:
                _note_redaction(name, n)
            return new

        s = _apply(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", 'openai_sk')
        s = _apply(r"ya29\.[A-Za-z0-9_\-\.]{8,}", "[REDACTED]", 'google_ya29')
        s = _apply(r"AIza[0-9A-Za-z\-_]{35,}", "[REDACTED]", 'google_api_key')
        s = _apply(r"bearer\s+[A-Za-z0-9\._\-\=]{8,}", "[REDACTED]", 'bearer_token', flags=re.I)
        s = _apply(r"(access_token|token)=([A-Za-z0-9_\-\.]{8,})", lambda m: f"{m.group(1)}=[REDACTED]", 'token_param', flags=re.I)
        s = _apply(r"(id_token|oauth_token|refresh_token)=([A-Za-z0-9_\-\. %]{8,})", lambda m: f"{m.group(1)}=[REDACTED]", 'other_token_params', flags=re.I)
        s = _apply(r"key=([A-Za-z0-9_\-\.]{8,})", "key=[REDACTED]", 'key_param', flags=re.I)
        s = _apply(r"AKIA[0-9A-Z]{16}", "[REDACTED]", 'aws_akid')
        s = _apply(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40,}(?![A-Za-z0-9/+=])", "[REDACTED]", 'long_base64')
        s = _apply(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----", "[REDACTED]", 'pem_private')
        s = _apply(r"-----BEGIN RSA PRIVATE KEY-----[\s\S]+?-----END RSA PRIVATE KEY-----", "[REDACTED]", 'pem_rsa')
        s = _apply(r"-----BEGIN OPENSSH PRIVATE KEY-----[\s\S]+?-----END OPENSSH PRIVATE KEY-----", "[REDACTED]", 'pem_openssh')
        s = _apply(r"-----BEGIN EC PRIVATE KEY-----[\s\S]+?-----END EC PRIVATE KEY-----", "[REDACTED]", 'pem_ec')
        s = _apply(r"ssh-(rsa|ed25519) [A-Za-z0-9+/=\.]{40,}", "[REDACTED]", 'ssh_blob')
        s = _apply(r"sig=([A-Za-z0-9%_\-\.]{16,})", "sig=[REDACTED]", 'azure_sig', flags=re.I)
        s = _apply(r"se=[0-9TZ:\-\.]+&?sig=[A-Za-z0-9%_\-\.]{8,}", "se=[REDACTED]&sig=[REDACTED]", 'azure_se_sig', flags=re.I)
        s = _apply(r"sig%3D([A-Za-z0-9%_\-\.]{8,})", "sig%3D[REDACTED]", 'azure_sig_encoded', flags=re.I)
        s = _apply(r"se%3D[0-9TZ%:\-\.]+%26?sig%3D[A-Za-z0-9%_\-\.]{8,}", "se%3D[REDACTED]%26sig%3D[REDACTED]", 'azure_se_sig_encoded', flags=re.I)
        s = _apply(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", "[REDACTED]", 'jwt')
        s = _apply(r"(?<![0-9a-fA-F])[0-9a-fA-F]{40,}(?![0-9a-fA-F])", "[REDACTED]", 'long_hex')
        s = _apply(r'"private_key"\s*:\s*"-----BEGIN [^\"]+-----[\s\S]+?-----END [^\"]+-----"', '"private_key":"[REDACTED]"', 'sa_private_key')
        s = _apply(r'"private_key_id"\s*:\s*"[0-9a-fA-F]{16,}"', '"private_key_id":"[REDACTED]"', 'sa_private_key_id')

        vendor_enabled = os.getenv('REDACT_VENDOR_PATTERNS', '').lower() in ('1', 'true', 'yes')
        if vendor_enabled:
            s = _apply(r"ghp_[A-Za-z0-9_]{36,}", "[REDACTED]", 'github_ghp')
            s = _apply(r"xox[pbo]-[A-Za-z0-9-]{8,}", "[REDACTED]", 'slack_xox')
            s = _apply(r"(sk_live|sk_test)_[A-Za-z0-9]{8,}", "[REDACTED]", 'stripe_sk', flags=re.I)

        extra = os.getenv('REDACT_VENDOR_REGEXES', '')
        try:
            global _COMPILED_VENDOR_REGEXES, _VENDOR_REGEXES_RAW
            with _VENDOR_LOCK if _VENDOR_LOCK is not None else _null_context():
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
                                            _note_vendor_error(pname)
                                            continue
                            else:
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
                        try:
                            total_budget_ms = int(os.getenv('REDACT_VENDOR_REGEX_TOTAL_TIMEOUT_MS', '200'))
                        except Exception:
                            total_budget_ms = 200
                        start_time = time.time()
                        for pname, cre, engine, _raw in _COMPILED_VENDOR_REGEXES:
                            elapsed_ms = (time.time() - start_time) * 1000.0
                            if elapsed_ms >= total_budget_ms:
                                _note_vendor_budget_exceeded()
                                break
                            try:
                                if engine == 'regex' and _REGEX_AVAILABLE:
                                    try:
                                        timeout_ms = int(os.getenv('REDACT_VENDOR_REGEX_TIMEOUT_MS', '100'))
                                    except Exception:
                                        timeout_ms = 100
                                    new, n = cre.subn("[REDACTED]", s, timeout=timeout_ms / 1000.0)
                                else:
                                    new, n = cre.subn("[REDACTED]", s)
                                if n:
                                    _note_redaction(pname, n)
                                    s = new
                            except Exception as e:
                                try:
                                    if _REGEX_AVAILABLE and isinstance(e, _regex.TimeoutError):
                                        _note_vendor_timeout(pname)
                                        continue
                                except Exception:
                                    pass
                                _note_vendor_error(pname)
                                continue
        except Exception:
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

    return obj


class _null_context:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False

"""Compatibility shim for task utilities.

Some modules import backend.tasks.utils.redact_secrets during the
refactor. Re-export the canonical redact_secrets implementation from
backend.utils.redaction to avoid import errors in test environments
that don't have the legacy module.
"""

from backend.utils.redaction import redact_secrets  # noqa: F401

__all__ = ["redact_secrets"]

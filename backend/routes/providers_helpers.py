# Small helpers extracted from providers routes to shorten the main file.
#
# Functions here are small, focused, and imported by the main
# backend.routes.providers.register to keep that file under the size
# threshold while preserving behavior.


def sanitize_provider_output(p):
    """Return a dict with non-sensitive provider fields."""
    return {
        "id": p.id,
        "workspace_id": p.workspace_id,
        "type": p.type,
        "secret_id": getattr(p, "secret_id", None),
        "last_tested_at": getattr(p, "last_tested_at", None),
    }

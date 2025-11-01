"""Executor that runs workflow graphs inline.

This module contains a refactored, narrower implementation extracted from
the original process_run. It is intended to be imported by backend.tasks
as the runtime executor. For this safe refactor step we implement a thin
version that delegates to the original logic where convenient to minimize
behavioral changes.
"""

import logging

logger = logging.getLogger(__name__)


def execute_process_run(run_db_id, node_id=None, node_graph=None, run_input=None):
    """Simple wrapper that imports the original implementation if still
    present (this keeps behavior identical while we split handlers out).

    As we continue the refactor we'll replace this with a composition of
    smaller handler modules. For now delegate to the legacy implementation
    when available.
    """
    try:
        # Import original heavy function if tests still rely on it
        from . import _legacy_process as _legacy  # type: ignore
        return _legacy.process_run(run_db_id, node_id=node_id, node_graph=node_graph, run_input=run_input)
    except Exception:
        # If legacy module not available, raise clear error for developer
        logger.exception("legacy process_run not available; executor not yet implemented")
        raise

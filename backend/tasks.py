import os
import logging

logger = logging.getLogger(__name__)

# Import-time sentinel so we can detect whether the worker loaded this module
try:
    logger.warning("tasks MODULE LOADED marker=LLMLOG_v1 pid=%s", os.getpid())
except Exception:
    logger.warning("tasks MODULE LOADED marker=LLMLOG_v1")

# Re-export small modules to keep this file as a shim during refactor.
from .events import _publish_redis_event  # noqa: E402
from .celery_app import celery_app, celery, CeleryAppStub  # noqa: E402


def _node_in_graph(node_graph, node_id):
    """Return True if node_id is present in node_graph.

    Accept common shapes: node_graph['nodes'] may be a dict keyed by id
    or a list of node dicts containing an 'id' field.
    """
    if not isinstance(node_graph, dict):
        return False
    nodes = node_graph.get("nodes")
    if nodes is None:
        return False
    if isinstance(nodes, dict):
        return node_id in nodes
    if isinstance(nodes, (list, tuple)):
        for n in nodes:
            if isinstance(n, dict) and n.get("id") == node_id:
                return True
    return False


def process_run(run_db_id, node_id=None, node_graph=None, run_input=None):
    """Compatibility wrapper for the refactored executor.

    The heavy lifting has been moved to backend.tasks.executor. Keep this
    function as a thin delegating shim to preserve import surface and
    function signature while the refactor is in progress.
    """
    try:
        from .executor import execute_process_run  # type: ignore
        return execute_process_run(run_db_id, node_id=node_id, node_graph=node_graph, run_input=run_input)
    except Exception:
        # Fallback: raise a clear error so callers can detect missing executor
        logger.exception("process_run compatibility wrapper failed to import executor")
        raise


# For completeness, expose an execute_workflow function which workers may call.
# In the real system this would be the Celery task entrypoint. Here it simply
# delegates to process_run after validating arguments.
def execute_workflow(run_db_id, node_id=None, node_graph=None, **kwargs):
    return process_run(run_db_id, node_id=node_id, node_graph=node_graph)

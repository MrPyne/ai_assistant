"""Package for route modules."""

# expose a register function aggregator
from .auth import register as register_auth
from .schedulers import register as register_schedulers
from .runs import register as register_runs
from .node import register as register_node
from .api import register as register_api


def register_all(app, ctx):
    # register modules in a predictable order
    register_auth(app, ctx)
    register_schedulers(app, ctx)
    register_runs(app, ctx)
    register_node(app, ctx)
    register_api(app, ctx)

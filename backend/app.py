# Lightweight bootstrap that creates the FastAPI app and registers routes
try:
    from fastapi import FastAPI
except Exception:
    # provide minimal FastAPI stand-in imported by tests in constrained envs
    class FastAPI:  # pragma: no cover
        def __init__(self, *args, **kwargs):
            self._routes = {}
            self._events = {'startup': [], 'shutdown': []}
        def on_event(self, name):
            def _decor(fn):
                if name not in self._events:
                    self._events[name] = []
                self._events[name].append(fn)
                return fn
            return _decor
        def get(self, path, **kwargs):
            def _decor(fn):
                self._routes[('GET', path)] = fn
                return fn
            return _decor
        def post(self, path, **kwargs):
            def _decor(fn):
                self._routes[('POST', path)] = fn
                return fn
            return _decor
        def put(self, path, **kwargs):
            def _decor(fn):
                self._routes[('PUT', path)] = fn
                return fn
            return _decor
        def delete(self, path, **kwargs):
            def _decor(fn):
                self._routes[('DELETE', path)] = fn
                return fn
            return _decor

from .routes import register_all

app = FastAPI()

# construct a small ctx exposing compatibility with existing api_routes
from .routes import _shared as _shared
_ctx = {
    'SessionLocal': getattr(_shared, 'SessionLocal', None),
    'models': getattr(_shared, 'models', None),
    '_DB_AVAILABLE': getattr(_shared, '_DB_AVAILABLE', False),
    '_users': getattr(_shared, '_users', {}),
    '_workspaces': getattr(_shared, '_workspaces', {}),
    '_schedulers': getattr(_shared, '_schedulers', {}),
    '_providers': getattr(_shared, '_providers', {}),
    '_secrets': getattr(_shared, '_secrets', {}),
    '_workflows': getattr(_shared, '_workflows', {}),
    '_webhooks': getattr(_shared, '_webhooks', {}),
    '_runs': getattr(_shared, '_runs', {}),
    '_next': getattr(_shared, '_next', {}),
    '_add_audit': getattr(_shared, '_add_audit', None),
    '_workspace_for_user': getattr(_shared, '_workspace_for_user', None),
    '_user_from_token': getattr(_shared, '_user_from_token', None),
}

# register all routes
try:
    register_all(app, _ctx)
except Exception:
    # avoid breaking constrained imports
    pass

# expose helpers expected by tests
from .routes import _shared
hash_password = _shared.hash_password
verify_password = _shared.verify_password

# debug
try:
    paths = [r for r in getattr(app, '_routes', {}).keys()]
    print('DEBUG: backend.app routes ->', paths)
except Exception:
    pass

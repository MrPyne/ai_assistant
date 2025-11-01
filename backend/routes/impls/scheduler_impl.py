from typing import Optional
from datetime import datetime

# Delegate to legacy shared_impls during safe refactor
from .. import shared_impls as _shared  # noqa: F401


def create_scheduler_impl(body, user_id):
    return _shared.create_scheduler_impl(body, user_id)


def list_scheduler_impl(wsid):
    return _shared.list_scheduler_impl(wsid)


def update_scheduler_impl(sid, body, wsid):
    return _shared.update_scheduler_impl(sid, body, wsid)


def delete_scheduler_impl(sid, wsid):
    return _shared.delete_scheduler_impl(sid, wsid)

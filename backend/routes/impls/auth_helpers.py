from typing import Optional
from datetime import datetime
import os

# Delegate to legacy shared_impls for now
from .. import shared_impls as _shared  # noqa: F401


def hash_password(password: str) -> str:
    return _shared.hash_password(password)


def verify_password(password: str, hashed: str) -> bool:
    return _shared.verify_password(password, hashed)


def _user_from_token(authorization: Optional[str]) -> Optional[int]:
    return _shared._user_from_token(authorization)


def _workspace_for_user(user_id: int) -> Optional[int]:
    return _shared._workspace_for_user(user_id)


def _add_audit(workspace_id: int, user_id: int, action: str, object_type: Optional[str] = None, object_id: Optional[int] = None, detail: Optional[str] = None):
    return _shared._add_audit(workspace_id, user_id, action, object_type=object_type, object_id=object_id, detail=detail)

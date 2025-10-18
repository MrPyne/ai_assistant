import json
from backend.tasks import _publish_redis_event


def test_event_id_deterministic_for_same_payload():
    ev = {
        'type': 'log',
        'run_id': 1,
        'node_id': 'n1',
        'level': 'info',
        'message': 'hello',
    }

    # Generate two event dicts with identical content (timestamp excluded)
    a = ev.copy()
    b = ev.copy()
    _publish_redis_event(a)
    _publish_redis_event(b)

    # When _publish_redis_event runs it injects event_id into the passed dict
    # (best-effort); ensure it's present and deterministic (same for same payload)
    e1 = a.get('event_id')
    e2 = b.get('event_id')
    assert e1 is not None
    assert e2 is not None
    assert e1 == e2

#!/usr/bin/env python3
"""
Backfill script to populate run_logs.event_id for historical rows.

Usage:
    python scripts/backfill_runlog_event_ids.py [--commit] [--batch-size N] [--limit M] [--run-id RUN_ID]

By default the script runs in dry-run mode (no DB writes). Use --commit to persist changes.

This script mirrors the server's event_id generation to ensure deterministic ids
match what the running application will compute for new events.
"""
import argparse
import json
import logging
import sys
import uuid
import hashlib
from typing import Any

# Ensure project root is on path so backend package imports work
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal
from backend import models

logger = logging.getLogger("backfill_event_ids")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _canonicalize(ev: Any) -> str:
    """Create a deterministic canonical string representation for an event.

    Mirrors the implementation used by backend.tasks._publish_redis_event:
    - If ev is not a dict, stringify it.
    - For dicts, make a shallow copy excluding the 'timestamp' key and sort keys.
    - Attempt to JSON dump with sort_keys; fall back to per-key serialization.
    """
    try:
        if not isinstance(ev, dict):
            return str(ev)
        c = {k: ev.get(k) for k in sorted(ev.keys()) if k != 'timestamp'}
        try:
            return json.dumps(c, sort_keys=True, ensure_ascii=False)
        except Exception:
            items = []
            for k in sorted(c.keys()):
                v = c.get(k)
                try:
                    items.append(f"{k}:{json.dumps(v, sort_keys=True, default=str)}")
                except Exception:
                    items.append(f"{k}:{str(v)}")
            return "|".join(items)
    except Exception:
        return str(ev)


def _compute_event_id(ev: Any) -> str:
    """Compute event_id using UUID5(namespace=URL) over canonical string, fallback to sha1 repr."""
    try:
        canon = _canonicalize(ev)
        namespace = uuid.NAMESPACE_URL
        return str(uuid.uuid5(namespace, canon))
    except Exception:
        try:
            h = hashlib.sha1()
            h.update(repr(ev).encode('utf-8'))
            return h.hexdigest()
        except Exception:
            return None


def parse_message_field(msg: Any):
    """Attempt to parse the stored RunLog.message field into a dict

    The application persists json.dumps(safe_event) for events; however older
    rows may contain different shapes. We try JSON parse and fall back to
    returning the original value.
    """
    if msg is None:
        return None
    if isinstance(msg, dict):
        return msg
    if isinstance(msg, (bytes, bytearray)):
        try:
            msg = msg.decode('utf-8')
        except Exception:
            return {'message': repr(msg)}
    if isinstance(msg, str):
        try:
            return json.loads(msg)
        except Exception:
            # not JSON: return as a string value under 'message'
            return {'message': msg}
    # unknown type: stringify
    try:
        return {'message': str(msg)}
    except Exception:
        return {'message': repr(msg)}


def backfill(commit=False, batch_size=500, limit=None, run_id=None):
    processed = 0
    updated = 0
    session = SessionLocal()
    try:
        while True:
            query = session.query(models.RunLog).filter(models.RunLog.event_id == None)
            if run_id is not None:
                query = query.filter(models.RunLog.run_id == run_id)
            # load in a deterministic order to allow safe resumability
            query = query.order_by(models.RunLog.id).limit(batch_size)
            rows = query.all()
            if not rows:
                logger.info("no more rows to process")
                break

            for rl in rows:
                processed += 1
                try:
                    parsed = parse_message_field(rl.message)
                    eid = _compute_event_id(parsed)
                    if not eid:
                        logger.warning("could not compute event_id for RunLog id=%s", rl.id)
                        continue
                    logger.debug("row id=%s run_id=%s node_id=%s -> event_id=%s", rl.id, rl.run_id, rl.node_id, eid)
                    if commit:
                        rl.event_id = eid
                        session.add(rl)
                        updated += 1
                except Exception:
                    logger.exception("failed processing run_log id=%s", rl.id)

                if limit is not None and processed >= limit:
                    break

            if commit:
                try:
                    session.commit()
                except Exception:
                    logger.exception("commit failed, attempting rollback")
                    session.rollback()
                    raise

            logger.info("processed=%s updated=%s", processed, updated)

            if limit is not None and processed >= limit:
                logger.info("reached processing limit of %s", limit)
                break

        return processed, updated
    finally:
        try:
            session.close()
        except Exception:
            pass


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--commit', action='store_true', help='Persist updates to the DB (default: dry-run)')
    p.add_argument('--batch-size', type=int, default=500)
    p.add_argument('--limit', type=int, default=None, help='Optional limit on rows to process')
    p.add_argument('--run-id', type=str, default=None, help='Optional run_id to restrict backfill to a single run')
    p.add_argument('--verbose', action='store_true')
    args = p.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    logger.info('starting backfill dry-run=%s batch_size=%s limit=%s run_id=%s', args.commit, args.batch_size, args.limit, args.run_id)
    processed, updated = backfill(commit=args.commit, batch_size=args.batch_size, limit=args.limit, run_id=args.run_id)
    logger.info('done processed=%s updated=%s', processed, updated)

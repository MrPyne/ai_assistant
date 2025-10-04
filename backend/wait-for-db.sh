#!/usr/bin/env sh
set -e

# wait-for-db.sh
# Simple script to wait for Postgres to be ready before starting the app.
python - <<'PY'
import os
import socket
import time
import sys
import urllib.parse

url = os.environ.get('DATABASE_URL', '')
if url.startswith('postgres'):
    p = urllib.parse.urlparse(url)
    host = p.hostname or 'db'
    port = p.port or 5432
    for _ in range(120):
        try:
            s = socket.create_connection((host, port), timeout=1)
            s.close()
            sys.exit(0)
        except Exception:
            time.sleep(1)
sys.exit(0)
PY

exec "$@"

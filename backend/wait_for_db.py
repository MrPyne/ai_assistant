"""
Wait for Postgres to be ready, then exec the provided command (uvicorn by default).
This avoids shell shebang issues with CRLF on Windows hosts by using a Python entrypoint.
"""
import os
import socket
import sys
import time
import urllib.parse
import subprocess
import shlex


def wait_for_postgres(url, timeout_seconds=120):
    if not url.startswith("postgres"):
        return
    p = urllib.parse.urlparse(url)
    host = p.hostname or "db"
    port = p.port or 5432
    start = time.time()
    while time.time() - start < timeout_seconds:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except Exception:
            time.sleep(1)
    # Timeout reached; continue anyway (uvicorn will fail and logs will show reason)


if __name__ == "__main__":
    database_url = os.environ.get("DATABASE_URL", "")
    wait_for_postgres(database_url)
    # Normalize line endings for any shell scripts in the mounted backend dir.
    # This helps when host files use CRLF (Windows) and are bind-mounted into the container.
    try:
        import pathlib

        backend_dir = pathlib.Path("/app/backend")
        if backend_dir.exists():
            for p in backend_dir.rglob("*.sh"):
                try:
                    # read as binary and replace CRLF -> LF
                    data = p.read_bytes()
                    if b"\r\n" in data:
                        p.write_bytes(data.replace(b"\r\n", b"\n"))
                except Exception:
                    # ignore file permission errors
                    pass
    except Exception:
        pass
    # default command
    cmd = [
        "uvicorn",
        "backend.app:app",
        "--host",
        "0.0.0.0",
        "--port",
        os.environ.get("PORT", "8000"),
    ]
    # allow passing alternate command args via CLI
    if len(sys.argv) > 1:
        cmd = sys.argv[1:]
    # execute the command (replace current process)
    os.execvp(cmd[0], cmd)

"""
Wait for Postgres to be ready, then exec the provided command (uvicorn by default).
This avoids shell shebang issues with CRLF on Windows hosts by using a Python entrypoint.

This script previously only attempted a TCP connect to the Postgres port. That can
succeed while Postgres is still recovering and responding with FATAL errors like
"the database system is starting up". To avoid racing the DB, we now attempt a
real DBAPI connection (if psycopg2 is available) and retry until a successful
connection can be established or a timeout is reached.
"""
import os
import socket
import sys
import time
import urllib.parse
import subprocess
import shlex
import traceback

try:
    import psycopg2
    from psycopg2 import OperationalError as Psycopg2OperationalError
except Exception:
    psycopg2 = None
    Psycopg2OperationalError = Exception

try:
    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig
except Exception:
    alembic_command = None
    AlembicConfig = None


def wait_for_postgres(url, timeout_seconds=120, interval_seconds=1.0):
    """Block until Postgres is ready or timeout is reached.

    If psycopg2 is available this attempts a real DBAPI connection to the
    target database (using the credentials in DATABASE_URL). If psycopg2 is not
    available we fall back to a TCP connect to the host:port.

    This function prints progress so container logs show what's happening.
    """
    if not url or not url.startswith("postgres"):
        print("No Postgres DATABASE_URL detected; skipping wait_for_postgres")
        return

    p = urllib.parse.urlparse(url)
    host = p.hostname or "db"
    port = p.port or 5432
    dbname = (p.path or "").lstrip('/') or 'postgres'
    user = urllib.parse.unquote(p.username or '')
    password = urllib.parse.unquote(p.password or '')

    deadline = time.time() + timeout_seconds
    attempt = 0

    print(f"Waiting for Postgres at {host}:{port} (database={dbname}) for up to {timeout_seconds}s")

    while True:
        attempt += 1
        # First ensure the TCP port is accepting connections; this gives faster
        # feedback than waiting for a DBAPI connect timeout.
        try:
            with socket.create_connection((host, port), timeout=1):
                pass
        except Exception:
            if time.time() >= deadline:
                print(f"Timed out waiting for TCP port {host}:{port}")
                return
            print(f"Postgres TCP port not open yet (attempt {attempt}); retrying in {interval_seconds}s")
            time.sleep(interval_seconds)
            continue

        # If psycopg2 is available, try a DBAPI connection to ensure Postgres is
        # past recovery and ready to accept queries. Connect to the target DB so
        # _maybe_create_database can rely on the server being responsive.
        if psycopg2:
            try:
                conn = psycopg2.connect(dbname=dbname or 'postgres', user=user or None, password=password or None, host=host, port=port, connect_timeout=3)
                conn.close()
                print(f"Successfully connected to Postgres (attempt {attempt})")
                return
            except Psycopg2OperationalError as exc:
                # This is expected while Postgres is starting up/recovering. Print
                # the error message for visibility and retry until timeout.
                msg = str(exc)
                if time.time() >= deadline:
                    print(f"Timed out waiting for Postgres: {msg}")
                    return
                print(f"Postgres not ready (attempt {attempt}): {msg}; retrying in {interval_seconds}s")
                time.sleep(interval_seconds)
                # gentle backoff
                interval_seconds = min(interval_seconds * 1.5, 10.0)
                continue
            except Exception as exc:
                # Non-OperationalError (e.g. authentication failure) — surface and stop
                print(f"Unexpected error while attempting to connect to Postgres: {exc}")
                raise
        else:
            # No psycopg2: TCP connect succeeded, assume Postgres is ready enough.
            print(f"TCP port open for Postgres (attempt {attempt}); continuing without DBAPI check (psycopg2 not installed)")
            return


def _maybe_create_database(database_url: str):
    """If DATABASE_URL points to a Postgres DB and that DB does not exist,
    attempt to create it by connecting to the default 'postgres' database.

    This is a convenience for local development and Docker Compose setups
    where the DB server is present but the specific database hasn't been
    created yet.
    """
    if not database_url or not database_url.startswith("postgres"):
        return
    if psycopg2 is None:
        print("psycopg2 not available; skipping database auto-creation")
        return
    p = urllib.parse.urlparse(database_url)
    target_db = (p.path or "").lstrip('/') or 'postgres'
    # If target is the default 'postgres' DB, no need to create
    if target_db == 'postgres':
        return

    host = p.hostname or 'localhost'
    port = p.port or 5432
    user = urllib.parse.unquote(p.username or '')
    password = urllib.parse.unquote(p.password or '')

    # Connect to the default 'postgres' database to manage DBs
    conn = None
    try:
        conn = psycopg2.connect(dbname='postgres', user=user or None, password=password or None, host=host, port=port)
        conn.set_session(autocommit=True)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
        exists = cur.fetchone() is not None
        if not exists:
            print(f"Creating database '{target_db}'...")
            cur.execute(f"CREATE DATABASE \"{target_db}\"")
            print("Database created")
        else:
            print(f"Database '{target_db}' already exists")
        cur.close()
    finally:
        if conn:
            conn.close()


def _run_alembic_migrations(database_url: str):
    """Run `alembic upgrade head` programmatically if alembic is available.

    This reads backend/alembic.ini and overrides sqlalchemy.url with the
    provided DATABASE_URL. It's best-effort for local/dev usage.
    """
    # If alembic isn't importable, provide a clear, actionable message.
    if not AlembicConfig or not alembic_command:
        msg = (
            "Alembic is not available in this environment; automatic migrations cannot be applied.\n"
            "Possible remediation steps:\n"
            "  - Install alembic in the runtime environment (e.g. `pip install alembic`) and restart the service.\n"
            "  - Run the helper script `scripts/apply_migrations.py` from a machine/container that has alembic available.\n"
            "  - Apply migrations manually using the alembic CLI.\n\n"
            "If you understand the risks and want the process to continue without running migrations, set the environment variable `FAIL_ON_MIGRATION_MISSING=0`.\n"
            "To make startup fail loudly when alembic is missing, set `FAIL_ON_MIGRATION_MISSING=1` and the process will abort."
        )
        print(msg)
        if os.environ.get("FAIL_ON_MIGRATION_MISSING") in ("1", "true", "True"):
            raise RuntimeError("Alembic not available and FAIL_ON_MIGRATION_MISSING set; aborting startup.")
        return
    # locate alembic.ini; prefer a backend/alembic.ini if present in the repo layout
    here = os.path.dirname(__file__)
    candidate_paths = [
        os.path.join(here, 'alembic.ini'),
        os.path.join(here, 'backend', 'alembic.ini'),
        os.path.join(here, 'backend', 'alembic.ini'),
    ]
    alembic_ini_path = None
    for p in candidate_paths:
        if os.path.exists(p):
            alembic_ini_path = p
            break
    if not alembic_ini_path:
        # last ditch: check relative to current working dir
        p = os.path.join(os.getcwd(), 'backend', 'alembic.ini')
        if os.path.exists(p):
            alembic_ini_path = p

    if not alembic_ini_path:
        print("alembic.ini not found; skipping migrations")
        return

    cfg = AlembicConfig(alembic_ini_path)
    # Ensure alembic can find the scripts folder even when script_location in
    # alembic.ini is a relative path. Make it absolute based on the ini file's
    # directory so Alembic doesn't try to resolve it relative to the process cwd.
    try:
        script_loc = cfg.get_main_option('script_location') or 'alembic'
        if not os.path.isabs(script_loc):
            abs_script_loc = os.path.normpath(os.path.join(os.path.dirname(alembic_ini_path), script_loc))
            if os.path.exists(abs_script_loc):
                cfg.set_main_option('script_location', abs_script_loc)
    except Exception:
        # If anything goes wrong, proceed and let alembic raise a clearer error.
        pass

    if database_url:
        # If the application uses an async DB driver (eg. postgresql+asyncpg://)
        # Alembic / the migration env expects a synchronous DBAPI URL. Strip
        # async driver markers so migrations run with the sync driver.
        db_url_for_alembic = database_url
        try:
            # common async marker used with SQLAlchemy async engines
            if "+asyncpg" in db_url_for_alembic:
                db_url_for_alembic = db_url_for_alembic.replace("+asyncpg", "")
        except Exception:
            # If anything strange happens, fall back to original URL and let
            # Alembic raise a clear error rather than crashing here.
            db_url_for_alembic = database_url
        cfg.set_main_option('sqlalchemy.url', db_url_for_alembic)
    print(f"Running alembic upgrade head using {alembic_ini_path}...")
    alembic_command.upgrade(cfg, 'head')


if __name__ == "__main__":
    database_url = os.environ.get("DATABASE_URL", "")
    # Allow tuning wait timeout via env var
    try:
        timeout = int(os.environ.get("WAIT_FOR_DB_TIMEOUT", "180"))
    except Exception:
        timeout = 180
    try:
        wait_for_postgres(database_url, timeout_seconds=timeout)
    except Exception:
        # In case of unexpected errors, print traceback and continue; the
        # subsequent steps will fail loudly if the DB is unavailable.
        print("Exception while waiting for Postgres:")
        traceback.print_exc()

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
    # Before executing the server, attempt to create the target database (if using Postgres)
    database_url = os.environ.get("DATABASE_URL", "")
    try:
        _maybe_create_database(database_url)
    except Exception:
        # Log the traceback but continue; the server will fail loudly if DB isn't available
        print("Failed to ensure database exists:")
        traceback.print_exc()

    # Run alembic migrations (best-effort)
    try:
        _run_alembic_migrations(database_url)
    except Exception:
        print("Failed to run alembic migrations:")
        traceback.print_exc()
        # Allow opting into aborting startup when migrations fail/errors occur
        if os.environ.get("FAIL_ON_MIGRATION_ERROR") in ("1", "true", "True"):
            print("FAIL_ON_MIGRATION_ERROR set; aborting startup.")
            sys.exit(1)
        print("Continuing without applying migrations (this may lead to runtime errors).")

    os.execvp(cmd[0], cmd)

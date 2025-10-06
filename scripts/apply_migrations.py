"""
Helper script to apply Alembic migrations to the application's database.

Usage:
    python scripts/apply_migrations.py

Behavior:
- Locates backend/alembic.ini in the repository.
- If the Alembic Python package is available, runs alembic.command.upgrade(cfg, 'head')
  programmatically after ensuring the config's script_location is resolved and
  overriding sqlalchemy.url with DATABASE_URL (handles async driver markers).
- If Alembic isn't installed, prints actionable instructions the developer can
  run (docker-compose or direct alembic CLI) and exits with non-zero code.

This script is intended for developer convenience (local machines / CI) and
provides clearer error messages when Alembic isn't present in the runtime
image.
"""
import os
import sys
import urllib.parse

HERE = os.path.dirname(__file__)
CANDIDATES = [
    os.path.join(HERE, '..', 'backend', 'alembic.ini'),
    os.path.join(HERE, '..', 'alembic.ini'),
    os.path.join(HERE, 'backend', 'alembic.ini'),
]

def find_alembic_ini():
    for p in CANDIDATES:
        p_abs = os.path.abspath(p)
        if os.path.exists(p_abs):
            return p_abs
    return None


def normalize_db_url(url: str) -> str:
    # If using an async driver like postgresql+asyncpg, strip the +asyncpg
    if not url:
        return url
    try:
        if "+asyncpg" in url:
            return url.replace("+asyncpg", "")
    except Exception:
        pass
    return url


def run_programmatic(alembic_ini_path: str, database_url: str):
    try:
        from alembic.config import Config as AlembicConfig
        from alembic import command as alembic_command
    except Exception as e:
        print("Alembic Python package not available for programmatic migrations:\n", str(e))
        return False

    cfg = AlembicConfig(alembic_ini_path)
    try:
        script_loc = cfg.get_main_option('script_location') or 'alembic'
        if not os.path.isabs(script_loc):
            abs_script_loc = os.path.normpath(os.path.join(os.path.dirname(alembic_ini_path), script_loc))
            if os.path.exists(abs_script_loc):
                cfg.set_main_option('script_location', abs_script_loc)
    except Exception:
        pass

    if database_url:
        db_url_for_alembic = normalize_db_url(database_url)
        cfg.set_main_option('sqlalchemy.url', db_url_for_alembic)

    print(f"Running Alembic programmatically using {alembic_ini_path}...")
    try:
        alembic_command.upgrade(cfg, 'head')
        print("Alembic migrations applied successfully.")
        return True
    except Exception as e:
        print("Failed to run Alembic programmatically:", e)
        return False


def main():
    alembic_ini = find_alembic_ini()
    if not alembic_ini:
        print("Could not locate alembic.ini. Looked at:")
        for p in CANDIDATES:
            print("  - ", os.path.abspath(p))
        sys.exit(2)

    database_url = os.environ.get('DATABASE_URL') or ''
    # Try programmatic approach first
    ok = run_programmatic(alembic_ini, database_url)
    if ok:
        sys.exit(0)

    # If programmatic fails because alembic package isn't present, provide
    # actionable CLI instructions to the developer.
    print("\nProgrammatic migration failed (Alembic package may be missing).")
    print("If you're running in Docker Compose, try:")
    print("  docker-compose exec backend alembic -c backend/alembic.ini upgrade head")
    print("Or from your host Python environment, install Alembic and run:")
    print("  pip install alembic\n  alembic -c backend/alembic.ini upgrade head")
    print("\nIf your DATABASE_URL uses an async driver (e.g. postgresql+asyncpg://),")
    print("ensure alembic.ini uses a sync driver or set the sqlalchemy.url accordingly.")
    sys.exit(3)


if __name__ == '__main__':
    main()

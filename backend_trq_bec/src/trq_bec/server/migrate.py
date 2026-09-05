from __future__ import annotations

import os
from pathlib import Path

import psycopg

from .config import get_settings


def main() -> None:
    settings = get_settings()
    migrations_dir = Path(os.environ.get("TRQ_BEC_MIGRATIONS_DIR", "migrations"))
    files = sorted(migrations_dir.glob("*.sql"))
    if not files:
        raise SystemExit(f"No SQL migrations found in {migrations_dir}")
    with psycopg.connect(settings.database_url, autocommit=True) as connection:
        for path in files:
            migrations_table_exists = connection.execute(
                "SELECT to_regclass('public.schema_migrations') IS NOT NULL"
            ).fetchone()[0]
            if migrations_table_exists:
                already_applied = connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = %s",
                    (path.stem,),
                ).fetchone()
                if already_applied:
                    print(f"Skipped {path.name} (already applied)")
                    continue
            connection.execute(path.read_text(encoding="utf-8"))
            print(f"Applied {path.name}")


if __name__ == "__main__":
    main()

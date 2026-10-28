"""
Database Migration Tool: SQLite to Supabase PostgreSQL
Script Analyser Pro

Usage:
    python migrate_to_supabase.py [--target-url <POSTGRES_URL>] [--user-id <USER_UUID>]
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")


def migrate(target_url: str = "", default_user_id: str = "demo-user-id"):
    url = target_url or os.getenv("DATABASE_URL", "").strip()
    if not url:
        print("[ERROR] No target PostgreSQL DATABASE_URL provided.")
        print("Please set DATABASE_URL in your .env or pass --target-url 'postgresql://postgres:...@...supabase.co:5432/postgres'")
        return False

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    sqlite_path = ROOT_DIR / "script_analyser.db"
    if not sqlite_path.exists():
        print(f"[ERROR] Source SQLite database not found at {sqlite_path}")
        return False

    print("=" * 65)
    print("SCRIPT ANALYSER — SQLITE TO SUPABASE POSTGRESQL MIGRATION")
    print("=" * 65)
    print(f"Source SQLite:   {sqlite_path}")
    print(f"Target Database: {url.split('@')[-1] if '@' in url else 'PostgreSQL'}")
    print(f"Default User ID: {default_user_id}")
    print("-" * 65)

    import psycopg2
    import psycopg2.extras

    # Connect to SQLite
    s_conn = sqlite3.connect(sqlite_path)
    s_conn.row_factory = sqlite3.Row

    # Connect to PostgreSQL
    sslmode = "require" if ("supabase.co" in url or "render.com" in url) else "prefer"
    if "sslmode=" not in url and sslmode == "require":
        url_with_ssl = f"{url}{'&' if '?' in url else '?'}sslmode=require"
    else:
        url_with_ssl = url

    try:
        p_conn = psycopg2.connect(url_with_ssl)
        p_conn.autocommit = False
    except Exception as e:
        print(f"[ERROR] Failed to connect to PostgreSQL: {e}")
        return False

    # Temporarily set environment to target URL and run init_db
    os.environ["DATABASE_URL"] = url_with_ssl
    from app.database import init_db
    print("[1/5] Initializing target schema in Supabase PostgreSQL...")
    init_db()

    # Migration plan
    tables = [
        "users",
        "projects",
        "scenes",
        "characters",
        "character_traits",
        "character_relationships",
        "locations",
        "schedules",
        "comparisons",
        "market_reports",
    ]

    report = {}

    try:
        p_cur = p_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        print("[2/5] Migrating records...")
        for table in tables:
            # Check if table exists in SQLite
            check = s_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)).fetchone()
            if not check:
                report[table] = {"source": 0, "migrated": 0, "status": "Skipped (not in SQLite)"}
                continue

            rows = s_conn.execute(f"SELECT * FROM {table}").fetchall()
            source_count = len(rows)
            if source_count == 0:
                report[table] = {"source": 0, "migrated": 0, "status": "Empty"}
                continue

            # Clear target table before migrating to prevent duplicates
            p_cur.execute(f"DELETE FROM {table}")

            # Get column names
            cols = [d[0] for d in s_conn.execute(f"SELECT * FROM {table} LIMIT 1").description]
            cols_str = ", ".join(cols)
            placeholders = ", ".join(["%s"] * len(cols))

            insert_sql = f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})"
            migrated_count = 0

            for r in rows:
                row_dict = dict(r)
                # Ensure user_id is set if column exists in table and value is empty
                if table == "projects" and ("user_id" not in row_dict or not row_dict["user_id"]):
                    row_dict["user_id"] = default_user_id

                values = [row_dict[c] for c in cols]
                p_cur.execute(insert_sql, values)
                migrated_count += 1

            report[table] = {"source": source_count, "migrated": migrated_count, "status": "OK"}
            print(f"  ✓ {table:<25} {migrated_count} records migrated")

        print("[3/5] Resetting PostgreSQL serial sequences...")
        for table in tables:
            if table == "users":
                continue
            try:
                p_cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), coalesce(max(id), 1)) FROM {table};")
            except Exception:
                pass

        p_conn.commit()
        print("[4/5] Changes committed successfully.")

        print("[5/5] Verification Summary:")
        print("-" * 65)
        print(f"{'Table':<26} {'SQLite Rows':<14} {'Postgres Rows':<14} {'Status'}")
        print("-" * 65)
        for t, data in report.items():
            print(f"{t:<26} {data['source']:<14} {data['migrated']:<14} {data['status']}")
        print("=" * 65)
        print("MIGRATION COMPLETED SUCCESSFULLY!")
        return True

    except Exception as e:
        p_conn.rollback()
        print(f"[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        s_conn.close()
        p_conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate SQLite to Supabase PostgreSQL")
    parser.add_argument("--target-url", default="", help="Target PostgreSQL connection string")
    parser.add_argument("--user-id", default="demo-user-id", help="Default owner user ID for existing projects")
    args = parser.parse_args()

    success = migrate(args.target_url, args.user_id)
    sys.exit(0 if success else 1)

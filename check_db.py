import sqlite3
from pathlib import Path

db = Path("script_analyser.db")
con = sqlite3.connect(db)

tables = con.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
      AND name NOT LIKE 'sqlite_%'
    ORDER BY name
""").fetchall()

print("SQLite database:", db.resolve())
print("-" * 45)

for (table,) in tables:
    count = con.execute(
        f'SELECT COUNT(*) FROM "{table}"'
    ).fetchone()[0]
    print(f"{table}: {count}")

con.close()

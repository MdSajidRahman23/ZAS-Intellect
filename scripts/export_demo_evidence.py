import sqlite3
import csv
from pathlib import Path

db_path = Path("zas_intellect.db")
out_dir = Path("demo_evidence")
out_dir.mkdir(exist_ok=True)

if not db_path.exists():
    print("Database not found. Skipping CSV export.")
    raise SystemExit

conn = sqlite3.connect(db_path)
cur = conn.cursor()

tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
target_tables = [t for t in tables if "proctor" in t.lower() or "event" in t.lower() or "audit" in t.lower()]

if not target_tables:
    print("No proctor/event/audit table found.")
    raise SystemExit

for table in target_tables:
    rows = cur.execute(f"SELECT * FROM {table}").fetchall()
    cols = [desc[0] for desc in cur.description]

    out_file = out_dir / f"{table}.csv"
    with out_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        writer.writerows(rows)

    print(f"Exported {len(rows)} rows -> {out_file}")

conn.close()

import sqlite3
from pathlib import Path
from database.config import DatabaseConfig

db_path = Path.home() / ".recall" / "recall.sqlite3"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.execute("SELECT project_id, name FROM projects")
for row in cursor.fetchall():
    print(f"ID: {row['project_id']}, Name: {row['name']}")
conn.close()

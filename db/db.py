from pathlib import Path

from peewee import SqliteDatabase


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "my_database.db"

db = SqliteDatabase(DB_PATH)

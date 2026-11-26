"""Database layer: PostgreSQL in production (DATABASE_URL), SQLite for local unit tests."""
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id {pk},
    title VARCHAR(200) NOT NULL,
    done BOOLEAN NOT NULL DEFAULT FALSE,
    priority VARCHAR(10) NOT NULL DEFAULT 'medium',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


class Database:
    def __init__(self, url=None):
        self.url = url or os.environ.get("DATABASE_URL", "sqlite:///:memory:")
        self.is_pg = self.url.startswith("postgres")
        self.ph = "%s" if self.is_pg else "?"
        self._sqlite = None
        if not self.is_pg:
            self._sqlite = sqlite3.connect(self.url.replace("sqlite:///", ""), check_same_thread=False)
            self._sqlite.row_factory = sqlite3.Row

    def _conn(self):
        if self.is_pg:
            import psycopg
            from psycopg.rows import dict_row
            return psycopg.connect(self.url, row_factory=dict_row, connect_timeout=3)
        return self._sqlite

    def query(self, sql, params=(), one=False, commit=False):
        sql = sql.replace("?", self.ph)
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()] if cur.description else []
            if commit:
                conn.commit()
            return (rows[0] if rows else None) if one else rows
        finally:
            if self.is_pg:
                conn.close()

    def init_schema(self):
        pk = "SERIAL PRIMARY KEY" if self.is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
        self.query(SCHEMA.format(pk=pk), commit=True)

    def ping(self):
        return self.query("SELECT 1 AS ok", one=True)["ok"] == 1

"""SQLite storage for chat history and analysed reports."""
import json
import sqlite3
from contextlib import contextmanager

from utils import DB_PATH, get_logger

log = get_logger(__name__)

EXPECTED_SCHEMA = {
    "chat_history": {
        "ddl": """CREATE TABLE chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        "columns": {"id", "session_id", "role", "content", "created_at"},
    },
    "reports": {
        "ddl": """CREATE TABLE reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            results TEXT,
            summary TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        "columns": {"id", "session_id", "filename", "results", "summary", "created_at"},
    },
}


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables; if an old table has a different structure, back it up and recreate."""
    with get_conn() as c:
        for table, spec in EXPECTED_SCHEMA.items():
            existing = {row["name"] for row in c.execute(f"PRAGMA table_info({table})")}
            if existing and not spec["columns"].issubset(existing):
                backup = f"{table}_old_backup"
                c.execute(f"DROP TABLE IF EXISTS {backup}")
                c.execute(f"ALTER TABLE {table} RENAME TO {backup}")
                log.warning("Old '%s' table had a different structure; renamed to '%s'.",
                            table, backup)
                existing = set()
            if not existing:
                c.execute(spec["ddl"])


def save_message(session_id: str, role: str, content: str) -> None:
    with get_conn() as c:
        c.execute("INSERT INTO chat_history (session_id, role, content) VALUES (?, ?, ?)",
                  (session_id, role, content))


def get_messages(session_id: str, limit: int = 100) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT role, content, created_at FROM chat_history WHERE session_id=? "
            "ORDER BY id DESC LIMIT ?", (session_id, limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


def clear_history(session_id: str) -> None:
    with get_conn() as c:
        c.execute("DELETE FROM chat_history WHERE session_id=?", (session_id,))


def save_report(session_id: str, filename: str, results: list[dict], summary: str) -> None:
    with get_conn() as c:
        c.execute("INSERT INTO reports (session_id, filename, results, summary) VALUES (?, ?, ?, ?)",
                  (session_id, filename, json.dumps(results), summary))


def get_reports(session_id: str) -> list[dict]:
    with get_conn() as c:
        rows = c.execute("SELECT * FROM reports WHERE session_id=? ORDER BY id DESC",
                         (session_id,)).fetchall()
    return [dict(r) for r in rows]
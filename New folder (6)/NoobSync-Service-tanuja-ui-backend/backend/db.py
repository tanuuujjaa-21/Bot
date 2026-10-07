"""
db.py
SQLite persistence for users, login sessions, chat history and documents.

One short-lived connection per call keeps this safe to use from FastAPI's
worker threads and the ingestion thread pool without sharing connections.
"""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    phone       TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    source          TEXT,
    latency_ms      REAL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename    TEXT NOT NULL,
    ext         TEXT NOT NULL,
    size_bytes  INTEGER NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL CHECK (status IN ('processing', 'ready', 'error')),
    error       TEXT,
    text_path   TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_docs_user ON documents(user_id, created_at DESC);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        # A restart interrupts any in-flight ingestion; don't leave those
        # documents spinning forever in the UI.
        conn.execute(
            "UPDATE documents SET status='error', "
            "error='Processing was interrupted. Remove this file and upload it again.' "
            "WHERE status='processing'"
        )
        conn.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (now_iso(),))


# ── Users ───────────────────────────────────────────────────────────────────
def phone_seen_before(phone: str) -> bool:
    with connect() as conn:
        return conn.execute(
            "SELECT 1 FROM users WHERE phone = ? LIMIT 1", (phone,)
        ).fetchone() is not None


def create_user(name: str, phone: str) -> dict:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (name, phone, created_at) VALUES (?, ?, ?)",
            (name, phone, now_iso()),
        )
        return {"id": cur.lastrowid, "name": name, "phone": phone}


def get_user(user_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, name, phone FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


# ── Login sessions ──────────────────────────────────────────────────────────
def save_auth_session(token_hash: str, user_id: int, expires_at: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (token_hash, user_id, now_iso(), expires_at),
        )


def user_for_token_hash(token_hash: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT u.id, u.name, u.phone FROM auth_sessions s "
            "JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > ?",
            (token_hash, now_iso()),
        ).fetchone()
        return dict(row) if row else None


def delete_auth_session(token_hash: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))


# ── Conversations & messages ────────────────────────────────────────────────
def create_conversation(user_id: int, title: str = "New chat") -> dict:
    cid, ts = new_id(), now_iso()
    with connect() as conn:
        conn.execute(
            "INSERT INTO conversations (id, user_id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (cid, user_id, title, ts, ts),
        )
    return {"id": cid, "title": title, "created_at": ts, "updated_at": ts}


def list_conversations(user_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations c "
            "WHERE user_id = ? "
            "AND EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id) "
            "ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_conversation(user_id: int, conversation_id: str) -> dict | None:
    """Returns the conversation only if it belongs to this user."""
    with connect() as conn:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations "
            "WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()
        return dict(row) if row else None


def delete_conversation(user_id: int, conversation_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        )
        return cur.rowcount > 0


def list_messages(conversation_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, role, content, source, latency_ms, created_at "
            "FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_exchange(
    conversation_id: str,
    question: str,
    answer: str,
    source: str | None,
    latency_ms: float | None,
    title_if_new: str,
) -> tuple[dict, dict]:
    """Stores a question and its answer together, so history never contains
    a question that was never answered."""
    ts_q, ts_a = now_iso(), now_iso()
    with connect() as conn:
        q = conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) "
            "VALUES (?, 'user', ?, ?)",
            (conversation_id, question, ts_q),
        )
        a = conn.execute(
            "INSERT INTO messages (conversation_id, role, content, source, latency_ms, created_at) "
            "VALUES (?, 'assistant', ?, ?, ?, ?)",
            (conversation_id, answer, source, latency_ms, ts_a),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ?, "
            "title = CASE WHEN title = 'New chat' THEN ? ELSE title END "
            "WHERE id = ?",
            (ts_a, title_if_new, conversation_id),
        )
        return (
            {"id": q.lastrowid, "role": "user", "content": question,
             "source": None, "latency_ms": None, "created_at": ts_q},
            {"id": a.lastrowid, "role": "assistant", "content": answer,
             "source": source, "latency_ms": latency_ms, "created_at": ts_a},
        )


# ── Documents ───────────────────────────────────────────────────────────────
def add_document(doc_id: str, user_id: int, filename: str, ext: str,
                 size_bytes: int, text_path: str) -> dict:
    ts = now_iso()
    with connect() as conn:
        conn.execute(
            "INSERT INTO documents (id, user_id, filename, ext, size_bytes, status, "
            "text_path, created_at) VALUES (?, ?, ?, ?, ?, 'processing', ?, ?)",
            (doc_id, user_id, filename, ext, size_bytes, text_path, ts),
        )
    return get_document(user_id, doc_id)


def get_document(user_id: int, doc_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id)
        ).fetchone()
        return dict(row) if row else None


def list_documents(user_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def count_documents(user_id: int) -> int:
    with connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM documents WHERE user_id = ?", (user_id,)
        ).fetchone()[0]


def set_document_status(doc_id: str, status: str, chunk_count: int = 0,
                        error: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE documents SET status = ?, chunk_count = ?, error = ? WHERE id = ?",
            (status, chunk_count, error, doc_id),
        )


def delete_document(user_id: int, doc_id: str) -> dict | None:
    doc = get_document(user_id, doc_id)
    if not doc:
        return None
    with connect() as conn:
        conn.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id))
    return doc

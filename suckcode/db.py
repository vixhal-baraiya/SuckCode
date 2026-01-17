"""SuckCode database - Session and conversation persistence."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from contextlib import contextmanager

# ═══════════════════════════════════════════════════════════════════════════════
# Database Configuration
# ═══════════════════════════════════════════════════════════════════════════════

DB_PATH = Path.home() / ".suckcode" / "suckcode.db"

# ═══════════════════════════════════════════════════════════════════════════════
# Schema
# ═══════════════════════════════════════════════════════════════════════════════

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    model TEXT,
    cwd TEXT,
    context TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    tool_calls TEXT,
    tool_call_id TEXT,
    created_at TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS file_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    path TEXT NOT NULL,
    action TEXT NOT NULL,
    content_before TEXT,
    content_after TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_file_changes_session ON file_changes(session_id);
"""

# ═══════════════════════════════════════════════════════════════════════════════
# Database Connection
# ═══════════════════════════════════════════════════════════════════════════════

def init_db():
    """Initialize the database and create tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA)

@contextmanager
def get_connection():
    """Get a database connection with proper cleanup."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

# ═══════════════════════════════════════════════════════════════════════════════
# Session Data Classes
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Session:
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    model: Optional[str] = None
    cwd: Optional[str] = None
    context: Optional[str] = None

@dataclass  
class Message:
    id: int
    session_id: str
    role: str
    content: Optional[str]
    tool_calls: Optional[list]
    tool_call_id: Optional[str]
    created_at: datetime
    tokens_used: int = 0

# ═══════════════════════════════════════════════════════════════════════════════
# Session Operations
# ═══════════════════════════════════════════════════════════════════════════════

def create_session(session_id: str, name: Optional[str] = None, model: Optional[str] = None) -> Session:
    """Create a new session."""
    now = datetime.now().isoformat()
    import os
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (id, name, created_at, updated_at, model, cwd) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, name or session_id, now, now, model, os.getcwd())
        )
    return Session(
        id=session_id,
        name=name or session_id,
        created_at=datetime.fromisoformat(now),
        updated_at=datetime.fromisoformat(now),
        model=model,
        cwd=os.getcwd()
    )

def get_session(session_id: str) -> Optional[Session]:
    """Get a session by ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row:
            return Session(
                id=row["id"],
                name=row["name"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                model=row["model"],
                cwd=row["cwd"],
                context=row["context"]
            )
    return None

def get_or_create_session(session_id: str, model: Optional[str] = None) -> Session:
    """Get existing session or create new one."""
    session = get_session(session_id)
    if session is None:
        session = create_session(session_id, model=model)
    return session

def list_sessions(limit: int = 20) -> list[Session]:
    """List recent sessions."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [
            Session(
                id=row["id"],
                name=row["name"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                model=row["model"],
                cwd=row["cwd"]
            )
            for row in rows
        ]

def delete_session(session_id: str):
    """Delete a session and all its messages."""
    with get_connection() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM file_changes WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

def update_session(session_id: str, **kwargs):
    """Update session fields."""
    with get_connection() as conn:
        updates = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [datetime.now().isoformat(), session_id]
        conn.execute(
            f"UPDATE sessions SET {updates}, updated_at = ? WHERE id = ?",
            values
        )

# ═══════════════════════════════════════════════════════════════════════════════
# Message Operations
# ═══════════════════════════════════════════════════════════════════════════════

def add_message(session_id: str, role: str, content: Optional[str] = None, 
                tool_calls: Optional[list] = None, tool_call_id: Optional[str] = None,
                tokens_used: int = 0) -> int:
    """Add a message to a session."""
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO messages (session_id, role, content, tool_calls, tool_call_id, created_at, tokens_used)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, role, content, json.dumps(tool_calls) if tool_calls else None, 
             tool_call_id, now, tokens_used)
        )
        # Update session timestamp
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (now, session_id)
        )
        return cursor.lastrowid

def get_messages(session_id: str, limit: Optional[int] = None) -> list[dict]:
    """Get messages for a session in API format."""
    with get_connection() as conn:
        query = "SELECT * FROM messages WHERE session_id = ? ORDER BY id"
        if limit:
            query += f" DESC LIMIT {limit}"
            rows = list(reversed(conn.execute(query, (session_id,)).fetchall()))
        else:
            rows = conn.execute(query, (session_id,)).fetchall()
        
        messages = []
        for row in rows:
            msg = {"role": row["role"]}
            if row["content"]:
                msg["content"] = row["content"]
            if row["tool_calls"]:
                msg["tool_calls"] = json.loads(row["tool_calls"])
            if row["tool_call_id"]:
                msg["tool_call_id"] = row["tool_call_id"]
            messages.append(msg)
        return messages

def clear_messages(session_id: str):
    """Clear all messages from a session."""
    with get_connection() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))

# ═══════════════════════════════════════════════════════════════════════════════
# File Change Tracking
# ═══════════════════════════════════════════════════════════════════════════════

def track_file_change(session_id: str, path: str, action: str,
                      content_before: Optional[str] = None,
                      content_after: Optional[str] = None):
    """Track a file change made during a session."""
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO file_changes (session_id, path, action, content_before, content_after, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, path, action, content_before, content_after, now)
        )

def get_file_changes(session_id: str) -> list[dict]:
    """Get all file changes for a session."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM file_changes WHERE session_id = ? ORDER BY id",
            (session_id,)
        ).fetchall()
        return [
            {
                "path": row["path"],
                "action": row["action"],
                "content_before": row["content_before"],
                "content_after": row["content_after"],
                "created_at": row["created_at"]
            }
            for row in rows
        ]

# ═══════════════════════════════════════════════════════════════════════════════
# Statistics
# ═══════════════════════════════════════════════════════════════════════════════

def get_session_stats(session_id: str) -> dict:
    """Get statistics for a session."""
    with get_connection() as conn:
        msg_count = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
        
        total_tokens = conn.execute(
            "SELECT SUM(tokens_used) FROM messages WHERE session_id = ?", (session_id,)
        ).fetchone()[0] or 0
        
        file_count = conn.execute(
            "SELECT COUNT(*) FROM file_changes WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
        
        return {
            "message_count": msg_count,
            "total_tokens": total_tokens,
            "file_changes": file_count
        }

# Initialize on import
init_db()

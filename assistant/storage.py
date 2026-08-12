"""
storage.py – Memoria de conversación del Asistente General, en SQLite.

Diseño deliberadamente simple para el "core compacto" de Jarvis: un único
archivo SQLite (sin contenedor extra, sin RAM adicional) que guarda el
historial de mensajes por usuario. Si más adelante se necesita algo más
robusto (PostgreSQL, Redis, etc.), se puede reemplazar este módulo sin
tocar `crew.py` ni `app.py` (ambos solo dependen de las funciones públicas
de aquí).
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("ASSISTANT_DB_PATH", "/app/data/assistant.db"))
MAX_HISTORY_MESSAGES = int(os.environ.get("ASSISTANT_MAX_HISTORY", "6"))


def _init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages (user_id, id)"
        )
        conn.commit()


@contextmanager
def _connection(path: Path = DB_PATH):
    _init_db(path)
    conn = sqlite3.connect(path)
    try:
        yield conn
    finally:
        conn.close()


def save_message(user_id: str, role: str, content: str, path: Path = DB_PATH) -> None:
    with _connection(path) as conn:
        conn.execute(
            "INSERT INTO messages (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (user_id, role, content, time.time()),
        )
        conn.commit()


def get_recent_history(
    user_id: str, limit: int = MAX_HISTORY_MESSAGES, path: Path = DB_PATH
) -> list[dict]:
    """Últimos `limit` mensajes de un usuario, en orden cronológico (más viejo primero)."""
    with _connection(path) as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [{"role": role, "content": content} for role, content in reversed(rows)]


def format_history_for_prompt(history: list[dict]) -> str:
    """Convierte el historial en texto plano legible para incluir en el prompt del agente."""
    if not history:
        return "(sin conversación previa)"
    lines = []
    for msg in history:
        speaker = "Usuario" if msg["role"] == "user" else "Jarvis"
        lines.append(f"{speaker}: {msg['content']}")
    return "\n".join(lines)

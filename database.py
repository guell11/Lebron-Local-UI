from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from threading import RLock
from typing import Any


class ChatDatabase:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    folder TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    meta TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_chats_updated ON chats(updated_at DESC);
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )

    def create_chat(self, title: str = "Nova conversa", folder: str = "") -> dict[str, Any]:
        now = time.time()
        chat_id = uuid.uuid4().hex
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO chats(id,title,folder,created_at,updated_at) VALUES(?,?,?,?,?)",
                (chat_id, title.strip()[:120] or "Nova conversa", folder.strip()[:80], now, now),
            )
        return self.get_chat(chat_id)

    def get_chat(self, chat_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
        if row is None:
            raise KeyError("Conversa não encontrada.")
        return dict(row)

    def list_chats(self, query: str = "", folder: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if query.strip():
            clauses.append("(c.title LIKE ? OR EXISTS (SELECT 1 FROM messages m WHERE m.chat_id=c.id AND m.content LIKE ?))")
            like = f"%{query.strip()}%"
            params.extend([like, like])
        if folder is not None:
            clauses.append("c.folder=?")
            params.append(folder)
        sql = "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.chat_id=c.id) AS message_count FROM chats c"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY c.updated_at DESC LIMIT 300"
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def update_chat(self, chat_id: str, *, title: str | None = None, folder: str | None = None) -> dict[str, Any]:
        fields: list[str] = []
        params: list[Any] = []
        if title is not None:
            fields.append("title=?")
            params.append(title.strip()[:120] or "Nova conversa")
        if folder is not None:
            fields.append("folder=?")
            params.append(folder.strip()[:80])
        fields.append("updated_at=?")
        params.append(time.time())
        params.append(chat_id)
        with self._lock, self._connect() as conn:
            cur = conn.execute(f"UPDATE chats SET {', '.join(fields)} WHERE id=?", params)
            if cur.rowcount == 0:
                raise KeyError("Conversa não encontrada.")
        return self.get_chat(chat_id)

    def delete_chat(self, chat_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM chats WHERE id=?", (chat_id,))

    def add_message(self, chat_id: str, role: str, content: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        if role not in {"system", "user", "assistant"}:
            raise ValueError("Papel de mensagem inválido.")
        now = time.time()
        message_id = uuid.uuid4().hex
        with self._lock, self._connect() as conn:
            exists = conn.execute("SELECT 1 FROM chats WHERE id=?", (chat_id,)).fetchone()
            if not exists:
                raise KeyError("Conversa não encontrada.")
            conn.execute(
                "INSERT INTO messages(id,chat_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?)",
                (message_id, chat_id, role, content, json.dumps(meta or {}, ensure_ascii=False), now),
            )
            conn.execute("UPDATE chats SET updated_at=? WHERE id=?", (now, chat_id))
        return {"id": message_id, "chat_id": chat_id, "role": role, "content": content, "meta": meta or {}, "created_at": now}

    def messages(self, chat_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE chat_id=? ORDER BY created_at ASC",
                (chat_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["meta"] = json.loads(item["meta"])
            except json.JSONDecodeError:
                item["meta"] = {}
            result.append(item)
        return result

    def maybe_title(self, chat_id: str, user_text: str) -> None:
        chat = self.get_chat(chat_id)
        if chat["title"] != "Nova conversa":
            return
        clean = " ".join(user_text.strip().split())
        if not clean:
            return
        title = clean[:54] + ("…" if len(clean) > 54 else "")
        self.update_chat(chat_id, title=title)

    def folders(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT DISTINCT folder FROM chats WHERE folder<>'' ORDER BY folder").fetchall()
        return [row[0] for row in rows]

    def list_notes(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM notes ORDER BY updated_at DESC").fetchall()]

    def save_note(self, note_id: str | None, title: str, content: str) -> dict[str, Any]:
        now = time.time()
        note_id = note_id or uuid.uuid4().hex
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO notes(id,title,content,created_at,updated_at) VALUES(?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET title=excluded.title, content=excluded.content, updated_at=excluded.updated_at
                """,
                (note_id, title.strip()[:120] or "Sem título", content, now, now),
            )
            row = conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
        return dict(row)

    def delete_note(self, note_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM notes WHERE id=?", (note_id,))

from __future__ import annotations

import json
import mimetypes
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from database import ChatDatabase
from runtime import RuntimeManager
from settings import SettingsStore
from system_info import system_snapshot

APP_ROOT = Path(__file__).resolve().parent
store = SettingsStore(APP_ROOT)
db = ChatDatabase(APP_ROOT / "data" / "lebron_ui.sqlite3")
runtime = RuntimeManager(APP_ROOT, store)
app = FastAPI(title="LeBRON Local UI", version="1.0.0")
app.mount("/static", StaticFiles(directory=APP_ROOT / "static"), name="static")


class SettingsPayload(BaseModel):
    settings: dict[str, Any]


class LoadPayload(BaseModel):
    settings: dict[str, Any] | None = None
    hf_token: str | None = Field(default=None, max_length=1000)


class ChatCreate(BaseModel):
    title: str = "Nova conversa"
    folder: str = ""


class ChatPatch(BaseModel):
    title: str | None = None
    folder: str | None = None


class StreamPayload(BaseModel):
    chat_id: str
    content: str = Field(min_length=1, max_length=100_000)
    attachments: list[dict[str, str]] = []
    generation: dict[str, Any] | None = None


class NotePayload(BaseModel):
    id: str | None = None
    title: str = "Sem título"
    content: str = ""


class DialogPayload(BaseModel):
    kind: str = "folder"
    title: str = "Selecionar caminho"


@app.get("/")
def index():
    return FileResponse(APP_ROOT / "templates" / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "runtime": runtime.status()}


@app.get("/api/settings")
def get_settings():
    return {"ok": True, "settings": store.load()}


@app.put("/api/settings")
def save_settings(payload: SettingsPayload):
    return {"ok": True, "settings": store.save(payload.settings)}


@app.post("/api/runtime/load")
def load_runtime(payload: LoadPayload):
    settings = payload.settings or store.load()
    store.save(settings)
    try:
        return {"ok": True, "runtime": runtime.load_async(settings, payload.hf_token)}
    except (RuntimeError, ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/runtime/unload")
def unload_runtime():
    try:
        return {"ok": True, "runtime": runtime.unload()}
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/runtime/stop")
def stop_runtime():
    runtime.stop()
    return {"ok": True}


@app.get("/api/runtime/status")
def runtime_status():
    return {"ok": True, "runtime": runtime.status()}


@app.get("/api/system")
def system():
    return {"ok": True, **system_snapshot()}


@app.get("/api/chats")
def list_chats(q: str = "", folder: str | None = None):
    return {"ok": True, "chats": db.list_chats(q, folder), "folders": db.folders()}


@app.post("/api/chats")
def create_chat(payload: ChatCreate):
    return {"ok": True, "chat": db.create_chat(payload.title, payload.folder)}


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str):
    try:
        return {"ok": True, "chat": db.get_chat(chat_id), "messages": db.messages(chat_id)}
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.patch("/api/chats/{chat_id}")
def patch_chat(chat_id: str, payload: ChatPatch):
    try:
        return {"ok": True, "chat": db.update_chat(chat_id, title=payload.title, folder=payload.folder)}
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str):
    db.delete_chat(chat_id)
    return {"ok": True}


@app.post("/api/chat/stream")
def chat_stream(payload: StreamPayload):
    try:
        db.get_chat(payload.chat_id)
        existing = db.messages(payload.chat_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    user_content = payload.content.strip()
    if payload.attachments:
        blocks = []
        for item in payload.attachments[:8]:
            name = str(item.get("name", "arquivo"))[:200]
            content = str(item.get("content", ""))[:60_000]
            blocks.append(f"\n\n--- Arquivo: {name} ---\n{content}")
        user_content += "".join(blocks)
    db.add_message(payload.chat_id, "user", user_content, {"attachments": [a.get("name") for a in payload.attachments]})
    db.maybe_title(payload.chat_id, payload.content)
    settings = store.load()
    messages = []
    system_prompt = str(settings.get("system_prompt") or "").strip()
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for item in existing[-40:]:
        if item["role"] in {"user", "assistant", "system"}:
            messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": user_content})
    generation = dict(settings.get("generation") or {})
    generation.update(payload.generation or {})

    def events():
        final_text = ""
        final_meta: dict[str, Any] = {}
        try:
            yield _ndjson({"event": "start"})
            for event in runtime.generate_stream(messages, generation):
                if event.get("event") == "done":
                    final_text = str(event.get("text") or final_text)
                    final_meta = {k: v for k, v in event.items() if k not in {"event", "text"}}
                elif event.get("event") == "token":
                    final_text += str(event.get("text") or "")
                yield _ndjson(event)
            if final_text.strip():
                db.add_message(payload.chat_id, "assistant", final_text.strip(), final_meta)
        except Exception as exc:  # noqa: BLE001
            yield _ndjson({"event": "error", "error": str(exc)})

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/files/read")
async def read_file(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(413, "Arquivo maior que 2 MB.")
    allowed = {".txt", ".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".csv", ".html", ".css", ".xml", ".log", ".sql"}
    suffix = Path(file.filename or "").suffix.lower()
    mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
    if suffix not in allowed and not mime.startswith("text/"):
        raise HTTPException(415, "Neste build, anexe apenas arquivos de texto/código.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1", errors="replace")
    return {"ok": True, "name": file.filename or "arquivo", "content": text}


@app.get("/api/notes")
def notes():
    return {"ok": True, "notes": db.list_notes()}


@app.post("/api/notes")
def save_note(payload: NotePayload):
    return {"ok": True, "note": db.save_note(payload.id, payload.title, payload.content)}


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: str):
    db.delete_note(note_id)
    return {"ok": True}


@app.post("/api/dialog")
def native_dialog(payload: DialogPayload):
    # Local desktop helper. It never runs when the app is hosted remotely without a desktop.
    kind = payload.kind.strip().lower()
    if kind not in {"file", "folder"}:
        raise HTTPException(400, "Tipo de seletor inválido.")
    title = payload.title.strip()[:120] or "Selecionar caminho"
    result: dict[str, str | None] = {"path": None}
    error: list[str] = []

    def open_dialog():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            if kind == "file":
                path = filedialog.askopenfilename(title=title, filetypes=[("Arquivos compatíveis", "*.pt *.gguf"), ("Todos", "*.*")])
            else:
                path = filedialog.askdirectory(title=title)
            result["path"] = path or None
            root.destroy()
        except Exception as exc:  # noqa: BLE001
            error.append(str(exc))

    thread = threading.Thread(target=open_dialog)
    thread.start()
    thread.join()
    if error:
        raise HTTPException(500, f"Não foi possível abrir o seletor nativo: {error[0]}")
    return {"ok": True, **result}



def _ndjson(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, default=str) + "\n").encode("utf-8")


@app.exception_handler(Exception)
async def unhandled(_request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"ok": False, "detail": str(exc)})

"""
FastAPI application — routes, CORS.
"""

import os
import sys
import uuid
import shutil
import asyncio
import tempfile
import logging

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, UploadFile, File, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware

from config import supabase
from models import (
    ChatRequest,
    ChatResponse,
    UploadResponse,
    Source,
)
from ingestion import ingest_document
from agent import get_crew_response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_DOCUMENTS_PER_SESSION = 3


def require_session_id(x_session_id: str = Header(..., alias="X-Session-Id")) -> str:
    """Every request must carry a client-generated session id.
    This is the sole privacy boundary between concurrent users — each session
    only ever sees/touches documents tagged with its own session_id.
    """
    if not x_session_id or not x_session_id.strip():
        raise HTTPException(status_code=400, detail="Missing X-Session-Id header.")
    return x_session_id.strip()


# ── App ────────────────────────────────────────────────────────────
app = FastAPI(
    title="DocMind",
    description="Agent-native document intelligence powered by CrewAI.",
    version="1.0.0",
)

# ── CORS ───────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ─────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Upload ─────────────────────────────────────────────────────────
@app.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    session_id: str = Depends(require_session_id),
):
    """Upload a PDF or TXT file for ingestion into the vector store.
    Scoped to the caller's session — max MAX_DOCUMENTS_PER_SESSION docs per session.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    allowed = (".pdf", ".txt")
    if not file.filename.lower().endswith(allowed):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed)}",
        )

    # Enforce per-session document cap before doing any work
    existing_count = (
        supabase.table("documents")
        .select("id", count="exact")
        .eq("session_id", session_id)
        .execute()
    )
    current_total = existing_count.count or 0
    if current_total >= MAX_DOCUMENTS_PER_SESSION:
        raise HTTPException(
            status_code=400,
            detail=(
                f"You've reached the limit of {MAX_DOCUMENTS_PER_SESSION} documents "
                f"for this session. Please delete one before uploading another."
            ),
        )

    suffix = os.path.splitext(file.filename)[1]
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, f"{uuid.uuid4()}{suffix}")

    try:
        with open(tmp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        doc_id, chunk_count, already_existed = await asyncio.to_thread(
            ingest_document, tmp_path, file.filename, session_id
        )

        return UploadResponse(
            doc_id=doc_id,
            filename=file.filename,
            chunk_count=chunk_count,
        )
    except Exception as e:
        error_str = str(e)
        if "SESSION_DOCUMENT_LIMIT_REACHED" in error_str:
            # The DB trigger is the source of truth for the cap — this branch
            # catches the rare race where two uploads passed the earlier
            # fast-path count check at nearly the same instant.
            raise HTTPException(
                status_code=400,
                detail=(
                    f"You've reached the limit of {MAX_DOCUMENTS_PER_SESSION} documents "
                    f"for this session. Please delete one before uploading another."
                ),
            )
        elif "0 chunks" in error_str.lower() or "empty" in error_str.lower():
            user_message = "This file doesn't appear to contain readable text. Please try a different PDF."
        elif "size" in error_str.lower() or "large" in error_str.lower():
            user_message = "This file is too large to process. Please try a smaller document."
        else:
            user_message = "Failed to upload the document. Please make sure it's a valid PDF or text file and try again."
        raise HTTPException(status_code=500, detail=user_message)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Document Library ───────────────────────────────────────────────
@app.get("/documents")
async def list_documents(session_id: str = Depends(require_session_id)):
    """Return documents belonging to the caller's session only."""
    result = (
        supabase.table("documents")
        .select("id, filename, created_at")
        .eq("session_id", session_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, session_id: str = Depends(require_session_id)):
    """Delete a document and its chunks (cascade via FK).
    Only the owning session can delete its own documents.
    """
    check = (
        supabase.table("documents")
        .select("id")
        .eq("id", doc_id)
        .eq("session_id", session_id)
        .execute()
    )
    if not check.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    supabase.table("documents").delete().eq("id", doc_id).eq("session_id", session_id).execute()
    return {"deleted": True, "doc_id": doc_id}


# ── Chat ───────────────────────────────────────────────────────────
@app.post("/chat")
def chat(request: ChatRequest, session_id: str = Depends(require_session_id)):
    try:
        answer, sources = get_crew_response(
            request.message, request.conversation_history, session_id=session_id
        )
        return ChatResponse(answer=answer, sources=sources)
    except Exception as e:
        import traceback
        traceback.print_exc()
        error_str = str(e)
        if "429" in error_str or "quota" in error_str.lower() or "RESOURCE_EXHAUSTED" in error_str:
            user_message = "I'm a bit overwhelmed right now — too many requests at once. Please wait a moment and try again."
        elif "timeout" in error_str.lower():
            user_message = "That took too long to process. Please try again."
        elif "connect" in error_str.lower() or "connection" in error_str.lower():
            user_message = "I'm having trouble connecting to my services. Please check your internet connection and try again."
        else:
            user_message = "Something went wrong on my end. Please try again in a moment."
        raise HTTPException(status_code=500, detail=user_message)
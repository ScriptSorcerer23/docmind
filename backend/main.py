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

from fastapi import FastAPI, UploadFile, File, HTTPException
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
async def upload_document(file: UploadFile = File(...)):
    """Upload a PDF or TXT file for ingestion into the vector store."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    allowed = (".pdf", ".txt")
    if not file.filename.lower().endswith(allowed):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed)}",
        )

    suffix = os.path.splitext(file.filename)[1]
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, f"{uuid.uuid4()}{suffix}")

    try:
        with open(tmp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        doc_id, chunk_count, already_existed = await asyncio.to_thread(
            ingest_document, tmp_path, file.filename
        )

        return UploadResponse(
            doc_id=doc_id,
            filename=file.filename,
            chunk_count=chunk_count,
        )
    except Exception as e:
        error_str = str(e)
        if "0 chunks" in error_str.lower() or "empty" in error_str.lower():
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
async def list_documents():
    """Return all uploaded documents."""
    result = (
        supabase.table("documents")
        .select("id, filename, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document and its chunks (cascade via FK)."""
    check = (
        supabase.table("documents")
        .select("id")
        .eq("id", doc_id)
        .execute()
    )
    if not check.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    supabase.table("documents").delete().eq("id", doc_id).execute()
    return {"deleted": True, "doc_id": doc_id}


# ── Chat ───────────────────────────────────────────────────────────
@app.post("/chat")
def chat(request: ChatRequest):
    try:
        answer, sources = get_crew_response(request.message, request.conversation_history)
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
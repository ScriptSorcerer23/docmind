"""
FastAPI application — routes, MCP SSE mount, and CORS configuration.
"""

import os
import uuid
import shutil
import tempfile

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from mcp.server.sse import SseServerTransport

from config import supabase
from models import (
    ChatRequest,
    ChatResponse,
    UploadResponse,
    DocumentRecord,
    Source,
)
from ingestion import ingest_document
from mcp_server import server as mcp_server_instance
from agent import get_crew_response

# ── App Initialization ─────────────────────────────────────────────
app = FastAPI(
    title="MCP-Powered RAG System",
    description="Document intelligence platform with MCP-native retrieval and CrewAI orchestration.",
    version="1.0.0",
)

# ── CORS ───────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",
        os.getenv("FRONTEND_URL", ""),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── MCP SSE Transport ─────────────────────────────────────────────
sse_transport = SseServerTransport("/mcp/messages")


@app.get("/mcp/sse")
async def mcp_sse_endpoint(request: Request):
    """SSE endpoint for MCP client connections."""
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp_server_instance.run(
            streams[0],
            streams[1],
            mcp_server_instance.create_initialization_options(),
        )


# ── Health Check ───────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "mcp-rag-backend"}


# ── Document Upload ────────────────────────────────────────────────
@app.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """Upload a PDF or TXT file for ingestion into the vector store."""
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    allowed_extensions = (".pdf", ".txt")
    if not file.filename.lower().endswith(allowed_extensions):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}",
        )

    # Save to temp file
    suffix = os.path.splitext(file.filename)[1]
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, f"{uuid.uuid4()}{suffix}")

    try:
        with open(tmp_path, "wb") as tmp_file:
            content = await file.read()
            tmp_file.write(content)

        # Run ingestion pipeline
        doc_id, chunk_count, already_existed = ingest_document(tmp_path, file.filename)

        return UploadResponse(
            doc_id=doc_id,
            filename=file.filename,
            chunk_count=chunk_count,
        )
    finally:
        # Cleanup temp files
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Document Library ───────────────────────────────────────────────
@app.get("/documents")
async def list_documents():
    """Return all uploaded documents for the frontend library panel."""
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
    # Verify document exists
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
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Send a message to the CrewAI agent.
    The agent decides whether to retrieve from documents or answer directly.
    """
    try:
        answer, sources = get_crew_response(
            message=request.message,
            conversation_history=request.conversation_history,
        )
        return ChatResponse(answer=answer, sources=sources)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

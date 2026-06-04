"""
Pydantic request/response models for all API endpoints.
"""

from pydantic import BaseModel
from typing import List, Optional


# ── Chat ───────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    conversation_history: List[dict] = []


class Source(BaseModel):
    filename: str
    chunk_preview: str
    page: Optional[int] = None
    similarity: Optional[float] = None


class ChatResponse(BaseModel):
    answer: str
    sources: List[Source] = []


# ── Documents ──────────────────────────────────────────────────────
class DocumentRecord(BaseModel):
    id: str
    filename: str
    created_at: str


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    chunk_count: int

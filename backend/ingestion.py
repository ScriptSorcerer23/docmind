"""
Document ingestion pipeline — load, chunk, embed, and store in Supabase pgvector.
"""

import hashlib
from typing import Tuple

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter

from config import supabase, embedder


# ── Helpers ────────────────────────────────────────────────────────

def compute_file_hash(file_path: str) -> str:
    """SHA-256 hash of file contents for idempotency checks."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            sha.update(block)
    return sha.hexdigest()


def check_existing_document(file_hash: str) -> dict | None:
    """Return existing document row if this file was already ingested."""
    result = (
        supabase.table("documents")
        .select("*")
        .eq("file_hash", file_hash)
        .execute()
    )
    if result.data:
        return result.data[0]
    return None


# ── Main Ingestion ─────────────────────────────────────────────────

def ingest_document(file_path: str, filename: str) -> Tuple[str, int, bool]:
    """
    Full ingestion pipeline.

    Returns:
        (doc_id, chunk_count, already_existed)
    """
    # 1. Idempotency check
    file_hash = compute_file_hash(file_path)
    existing = check_existing_document(file_hash)
    if existing:
        # Count existing chunks
        count_result = (
            supabase.table("document_chunks")
            .select("id", count="exact")
            .eq("doc_id", existing["id"])
            .execute()
        )
        chunk_count = count_result.count or 0
        return existing["id"], chunk_count, True

    # 2. Register document
    doc_row = (
        supabase.table("documents")
        .insert({"filename": filename, "file_hash": file_hash})
        .execute()
    )
    doc_id = doc_row.data[0]["id"]

    # 3. Load document
    if filename.lower().endswith(".pdf"):
        loader = PyPDFLoader(file_path)
    else:
        loader = TextLoader(file_path, encoding="utf-8")
    pages = loader.load()

    # 4. Chunk
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n\n", "\n", ".", " "],
    )
    chunks = splitter.split_documents(pages)

    if not chunks:
        return doc_id, 0, False

    # 5. Embed
    texts = [c.page_content for c in chunks]
    embeddings = embedder.embed_documents(texts)

    # 6. Batch insert (groups of 100 to respect Supabase limits)
    rows = [
        {
            "doc_id": doc_id,
            "content": chunks[i].page_content,
            "embedding": embeddings[i],
            "metadata": chunks[i].metadata,  # includes page number
        }
        for i in range(len(chunks))
    ]

    for i in range(0, len(rows), 100):
        supabase.table("document_chunks").insert(rows[i : i + 100]).execute()

    return doc_id, len(chunks), False

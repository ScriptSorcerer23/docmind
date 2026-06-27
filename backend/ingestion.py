"""
Document ingestion pipeline — load, chunk, embed, store in Supabase pgvector.
Uses Google text-embedding-004 (768-dim).
"""

import hashlib
import traceback
from typing import Tuple

from langchain_community.document_loaders import PyPDFLoader, PyMuPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import supabase, embedder


# ── Helpers ────────────────────────────────────────────────────────

def compute_file_hash(file_path: str) -> str:
    """MD5 hash of file contents for idempotency checks."""
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            md5.update(block)
    return md5.hexdigest()


def load_pdf(file_path: str):
    # Try PyPDFLoader first
    loader = PyPDFLoader(file_path)
    pages = loader.load()
    total_chars = sum(len(p.page_content) for p in pages)
    
    # If no text extracted, fall back to PyMuPDFLoader
    if total_chars == 0:
        print("[INGEST] PyPDFLoader returned 0 chars — falling back to PyMuPDFLoader")
        loader = PyMuPDFLoader(file_path)
        pages = loader.load()
        total_chars = sum(len(p.page_content) for p in pages)
    
    # If still 0, the PDF is a scanned image — return empty with warning
    if total_chars == 0:
        print("[INGEST] WARNING: PDF appears to be a scanned image with no extractable text. OCR required.")
    
    return pages


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

def ingest_document(file_path: str, filename: str, session_id: str) -> Tuple[str, int, bool]:
    """
    Full ingestion pipeline, scoped to the uploading session.

    Returns:
        (doc_id, chunk_count, already_existed)
    """
    print(f"\n{'='*60}")
    print(f"[INGEST] Starting ingestion for: {filename}")
    print(f"[INGEST] File path: {file_path}")

    # 1. Idempotency check via MD5 hash
    try:
        file_hash = compute_file_hash(file_path)
        print(f"[INGEST] File hash (MD5): {file_hash}")
    except Exception:
        print("[INGEST] ERROR computing file hash:")
        traceback.print_exc()
        raise

    # 1b. Look up whether this exact file was already ingested by THIS session
    try:
        print(f"[INGEST] Checking Supabase 'documents' table for existing file_hash in this session...")
        existing = (
            supabase.table("documents")
            .select("id")
            .eq("file_hash", file_hash)
            .eq("session_id", session_id)
            .execute()
        )
        print(f"[INGEST] Existing-document lookup returned {len(existing.data) if existing.data else 0} row(s)")
    except Exception:
        print("[INGEST] ERROR checking for existing document (file_hash lookup failed):")
        traceback.print_exc()
        raise

    if existing.data:
        doc_id = existing.data[0]["id"]
        # Check if chunks actually exist
        chunks_check = supabase.table("document_chunks").select("id").eq("doc_id", doc_id).limit(1).execute()
        if chunks_check.data:
            print(f"[INGEST] Document already ingested with {doc_id}, skipping.")
            return doc_id, 0, True
        else:
            print(f"[INGEST] Document record exists but chunks missing — re-ingesting.")
            # Delete the stale document record and re-ingest
            supabase.table("documents").delete().eq("id", doc_id).execute()

    # 2. Register document in Supabase, tagged with the owning session
    try:
        print(f"[INGEST] Registering document in 'documents' table...")
        doc_row = (
            supabase.table("documents")
            .insert({"filename": filename, "file_hash": file_hash, "session_id": session_id})
            .execute()
        )
        doc_id = doc_row.data[0]["id"]
        print(f"[INGEST] Document registered with id={doc_id}")
    except Exception:
        print("[INGEST] ERROR registering document in Supabase:")
        traceback.print_exc()
        raise

    # 3. Load document with LangChain
    try:
        print(f"[INGEST] Loading file with LangChain (type: {'PDF' if filename.lower().endswith('.pdf') else 'Text'})...")
        print(f"Loading file: {file_path}")
        if filename.lower().endswith(".pdf"):
            pages = load_pdf(file_path)
        else:
            loader = TextLoader(file_path, encoding="utf-8")
            pages = loader.load()
        print(f"[INGEST] Pages loaded: {len(pages)}")
        print(f"Pages loaded: {len(pages)}")
        for i, p in enumerate(pages[:3]):  # preview first 3 pages
            preview = p.page_content[:120].replace('\n', ' ')
            print(f"[INGEST]   Page {i}: {len(p.page_content)} chars | preview: '{preview}'")
        if len(pages) > 3:
            print(f"[INGEST]   ... ({len(pages) - 3} more pages)")
    except Exception:
        print("[INGEST] ERROR loading document:")
        traceback.print_exc()
        raise

    # 4. Chunk with RecursiveCharacterTextSplitter
    try:
        print(f"[INGEST] Splitting into chunks (size=800, overlap=100)...")
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=100,
            separators=["\n\n", "\n", ".", " "],
        )
        chunks = splitter.split_documents(pages)
        print(f"[INGEST] Chunks created: {len(chunks)}")
        print(f"Chunks created: {len(chunks)}")
        if not chunks:
            print("[INGEST] WARNING: 0 chunks produced — document appears empty or unreadable!")
            # Print raw page content lengths to diagnose
            for i, p in enumerate(pages):
                print(f"[INGEST]   Page {i} raw content length: {len(p.page_content)} | repr: {repr(p.page_content[:80])}")
            # Clean up registered document since it has no chunks
            supabase.table("documents").delete().eq("id", doc_id).execute()
            raise ValueError("0 chunks produced — document appears empty or unreadable!")
        for i, c in enumerate(chunks[:3]):  # preview first 3 chunks
            preview = c.page_content[:80].replace('\n', ' ')
            print(f"[INGEST]   Chunk {i}: {len(c.page_content)} chars | '{preview}'")
        if len(chunks) > 3:
            print(f"[INGEST]   ... ({len(chunks) - 3} more chunks)")
    except Exception:
        print("[INGEST] ERROR splitting document:")
        traceback.print_exc()
        raise

    # 5. Embed with Google text-embedding-004 (768-dim)
    try:
        print(f"[INGEST] Generating embeddings for {len(chunks)} chunks...")
        texts = [c.page_content for c in chunks]
        embeddings = embedder.embed_documents(texts)
        print(f"[INGEST] Embeddings generated: {len(embeddings)} (dim={len(embeddings[0]) if embeddings else 'N/A'})")
        print(f"Embeddings generated: {len(embeddings)}")
    except Exception:
        print("[INGEST] ERROR generating embeddings:")
        traceback.print_exc()
        raise

    # 6. Batch insert into document_chunks (groups of 100)
    try:
        rows = [
            {
                "doc_id": doc_id,
                "content": chunks[i].page_content,
                "embedding": embeddings[i],
                "metadata": {
                    "page": chunks[i].metadata.get("page", 0),
                    "chunk_index": i,
                },
            }
            for i in range(len(chunks))
        ]
        print(f"[INGEST] Inserting {len(rows)} rows into 'document_chunks' (batches of 100)...")
        print(f"Inserting {len(rows)} rows into document_chunks")

        for batch_start in range(0, len(rows), 100):
            batch = rows[batch_start : batch_start + 100]
            print(f"[INGEST]   Inserting batch [{batch_start}:{batch_start + len(batch)}]...")
            response = supabase.table("document_chunks").insert(batch).execute()
            print(f"Insert response: {response}")
            inserted = len(response.data) if response.data else 0
            print(f"[INGEST]   Batch insert response: {inserted} rows confirmed")

        print(f"[INGEST] SUCCESS — ingestion complete for '{filename}': {len(chunks)} chunks stored")
        print(f"{'='*60}\n")
    except Exception:
        print("[INGEST] ERROR inserting chunks into Supabase:")
        traceback.print_exc()
        raise

    return doc_id, len(chunks), False
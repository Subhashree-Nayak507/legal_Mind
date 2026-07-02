"""
Ingest route — minimal changes from original.

Changes:
  - chunk sizes now come from config (not hardcoded)
  - file size limit from config (not hardcoded 10MB)
  - structured logging added
  - embedder runs in thread pool (was blocking event loop)
"""
import asyncio
import os
import time
import uuid
import logging

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends

from app.services.chunker import extract_text, build_parent_child_chunks, SUPPORTED_EXTENSIONS
from app.services.embedder import embed_batch
from app.db.postgres import store_chunks
from app.core.config import settings
from app.core.logging import get_logger
from app.auth.dependencies import get_current_user

router = APIRouter()
logger = get_logger(__name__)


@router.post("/ingest")
async def ingest_document(
    file: UploadFile = File(...), user: dict = Depends(get_current_user)
):
    start = time.monotonic()
    user_id = user["id"]

    if not file:
        raise HTTPException(400, "No file uploaded.")

    # Validate extension
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            400, f"Unsupported format '{ext}'. Accepted: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    file_bytes = await file.read()

    # Validate size
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(400, f"File too large. Max {settings.max_file_size_mb}MB.")

    doc_id = str(uuid.uuid4())

    # Extract text
    raw_text = extract_text(file_bytes, file.filename)
    if not raw_text.strip():
        raise HTTPException(422, "Could not extract text from this file.")

    # Chunk with legal-optimised sizes from config
    chunks = build_parent_child_chunks(
        raw_text,
        parent_size=settings.parent_chunk_size,
        child_size=settings.child_chunk_size,
        overlap=settings.chunk_overlap,
    )

    # Embed child chunks only (parents are fetched by ID, not searched by vector)
    child_texts = [c["text"] for c in chunks if c["chunk_type"] == "child"]

    # Run embedding in thread pool — sentence-transformers is CPU-bound
    child_embeddings = await asyncio.to_thread(embed_batch, child_texts) if child_texts else []

    emb_iter = iter(child_embeddings)
    records = []
    for c in chunks:
        rec = {"doc_id": doc_id, "user_id": user_id, "filename": file.filename, **c}
        if c["chunk_type"] == "child":
            rec["embedding"] = next(emb_iter)
        records.append(rec)

    await store_chunks(records)

    child_count = sum(1 for c in chunks if c["chunk_type"] == "child")
    parent_count = sum(1 for c in chunks if c["chunk_type"] == "parent")
    elapsed_ms = int((time.monotonic() - start) * 1000)

    logger.info(
        "[Ingest] %s done in %dms — %d parents, %d children stored",
        file.filename, elapsed_ms, parent_count, child_count,
    )

    return {
        "doc_id":         doc_id,
        "filename":       file.filename,
        "format":         ext,
        "parent_chunks":  parent_count,
        "child_chunks":   child_count,
        "latency_ms":     elapsed_ms,
    }

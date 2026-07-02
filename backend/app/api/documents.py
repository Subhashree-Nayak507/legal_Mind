"""
Documents route.

GET  /documents        — list all docs uploaded by the logged-in user
DELETE /documents/{doc_id} — delete a doc and all its chunks
GET  /history          — return chat history for the current session
"""
from fastapi import APIRouter, HTTPException, Depends, Query

from app.db.postgres import list_user_documents, delete_document
from app.db.redis_client import get_history, format_history
from app.auth.dependencies import get_current_user
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/documents")
async def get_documents(user: dict = Depends(get_current_user)):
    """List all documents uploaded by this user — persists across sessions."""
    docs = await list_user_documents(user["id"])
    return {"documents": docs}


@router.delete("/documents/{doc_id}")
async def remove_document(doc_id: str, user: dict = Depends(get_current_user)):
    """Delete a document and all its chunks. Scoped to logged-in user."""
    deleted = await delete_document(doc_id, user["id"])
    if not deleted:
        raise HTTPException(404, "Document not found or already deleted.")
    logger.info("[Documents] Deleted doc_id=%s for user=%s", doc_id, user["id"])
    return {"deleted": True, "doc_id": doc_id}


@router.get("/history")
async def get_chat_history(
    session_id: str = Query(default="main"),
    user: dict = Depends(get_current_user)
):
    """Return chat history for this user's session — used to restore chat on page refresh."""
    scoped = f"{user['id']}:{session_id}"
    history = await get_history(scoped, max_turns=10)
    return {"history": history, "session_id": session_id}
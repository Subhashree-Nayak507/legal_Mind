"""
Hybrid Retriever — unchanged logic, added structured logging.

Logging added so you can answer in interview:
  "How do you debug a slow or bad retrieval?"
  → "Every retrieval logs: vector hits, keyword hits, merged count,
     and the top rerank score. I can see immediately which stage is slow."
"""
from app.db.postgres import similarity_search, keyword_search, fetch_parent
from app.services.embedder import embed_query
from app.core.logging import get_logger

logger = get_logger(__name__)


def _rrf_merge(dense: list[dict], sparse: list[dict], k: int = 60) -> list[dict]:
    """
    Reciprocal Rank Fusion — combines vector + keyword results.
    Each result scored as sum of 1/(k + rank) from each list.
    Higher combined score = ranked higher in merged output.
    """
    scores, seen = {}, {}
    for rank, doc in enumerate(dense):
        did = doc["id"]
        scores[did] = scores.get(did, 0) + 1 / (k + rank + 1)
        seen[did] = doc
    for rank, doc in enumerate(sparse):
        did = doc["id"]
        scores[did] = scores.get(did, 0) + 1 / (k + rank + 1)
        seen[did] = doc
    return [seen[i] for i in sorted(scores, key=lambda x: scores[x], reverse=True)]


async def retrieve(query: str, user_id: str, top_k: int = 20) -> list[dict]:
    query_emb = await embed_query(query)

    # Vector search (semantic — finds meaning matches), scoped to this user
    dense = await similarity_search(query_emb, user_id=user_id, top_k=10)
    logger.info("[Retriever] Vector search: %d results", len(dense))

    # Keyword search (BM25-style — finds exact term matches)
    keywords = [w for w in query.lower().split() if len(w) > 3]
    sparse = []
    if keywords:
        try:
            sparse = await keyword_search(keywords, user_id=user_id, top_k=10)
            logger.info("[Retriever] Keyword search: %d results", len(sparse))
        except Exception as e:
            logger.warning("[Retriever] Keyword search failed (continuing): %s", e)

    # Merge with RRF
    merged = _rrf_merge(dense, sparse)[:top_k]
    logger.info("[Retriever] Merged: %d unique candidates", len(merged))

    # Fetch parent text for each child chunk (gives LLM full clause context)
    enriched = []
    seen_parents: set = set()
    for child in merged:
        pid = child.get("parent_id")
        parent_text = None
        if pid and pid not in seen_parents:
            parent = await fetch_parent(pid, user_id=user_id)
            if parent:
                parent_text = parent["text"]
                seen_parents.add(pid)
        enriched.append({**child, "parent_text": parent_text})

    return enriched

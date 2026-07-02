"""
PostgreSQL — unchanged logic, updated to use config + structured logging.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from app.db.models import Base
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,    # detect dead connections before use
    pool_recycle=3600,     # recycle connections hourly
    echo=False,
)

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS doc_chunks_emb_idx
            ON document_chunks USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            WHERE embedding IS NOT NULL
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS doc_chunks_fts_idx
            ON document_chunks
            USING gin(to_tsvector('english', text))
        """))
    logger.info("[DB] Initialized: pgvector + HNSW + FTS indexes ready")


async def store_chunks(records: list[dict]):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            from app.db.models import DocumentChunk
            parent_map = {}

            for rec in records:
                if rec.get("chunk_type") == "parent":
                    chunk = DocumentChunk(
                        doc_id=rec["doc_id"], user_id=rec["user_id"],
                        filename=rec["filename"],
                        chunk_index=rec["chunk_index"], chunk_type="parent",
                        parent_id=None, text=rec["text"], embedding=None,
                    )
                    session.add(chunk)
                    await session.flush()
                    parent_map[rec["chunk_index"]] = chunk.id

            for rec in records:
                if rec.get("chunk_type") == "child":
                    db_parent_id = parent_map.get(rec.get("parent_chunk_index"))
                    chunk = DocumentChunk(
                        doc_id=rec["doc_id"], user_id=rec["user_id"],
                        filename=rec["filename"],
                        chunk_index=rec["chunk_index"], chunk_type="child",
                        parent_id=db_parent_id, text=rec["text"],
                        embedding=rec["embedding"],
                    )
                    session.add(chunk)


async def similarity_search(
    query_embedding: list[float], user_id: str, top_k: int = 10
) -> list[dict]:
    # WHERE user_id = :uid scopes every search to the caller's own documents.
    # This is the multi-tenancy fix — without it, this query would return
    # every user's chunks ranked together.
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, doc_id, filename, chunk_index, chunk_type, parent_id, text,
                       1 - (embedding <=> CAST(:emb AS vector)) AS score
                FROM document_chunks
                WHERE chunk_type = 'child' AND embedding IS NOT NULL
                  AND user_id = :uid
                ORDER BY embedding <=> CAST(:emb AS vector)
                LIMIT :k
            """),
            {"emb": str(query_embedding), "uid": user_id, "k": top_k},
        )
        return [dict(r._mapping) for r in result.fetchall()]


async def fetch_parent(parent_id: int, user_id: str) -> dict | None:
    # user_id check here too — prevents fetching another user's parent
    # chunk even if its id were guessed/leaked.
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, doc_id, filename, chunk_index, text
                FROM document_chunks WHERE id = :pid AND user_id = :uid
            """),
            {"pid": parent_id, "uid": user_id},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None


async def keyword_search(
    keywords: list[str], user_id: str, top_k: int = 10
) -> list[dict]:
    async with AsyncSessionLocal() as session:
        query_str = " | ".join(keywords)
        result = await session.execute(
            text("""
                SELECT id, doc_id, filename, chunk_index, chunk_type, parent_id, text,
                       ts_rank(to_tsvector('english', text), to_tsquery('english', :q)) AS score
                FROM document_chunks
                WHERE chunk_type = 'child'
                  AND user_id = :uid
                  AND to_tsvector('english', text) @@ to_tsquery('english', :q)
                ORDER BY score DESC
                LIMIT :k
            """),
            {"q": query_str, "uid": user_id, "k": top_k},
        )
        return [dict(r._mapping) for r in result.fetchall()]


# ── User account functions ──────────────────────────────────────────────────

async def create_user(email: str, hashed_password: str, name: str | None = None) -> dict:
    from app.db.models import User
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = User(email=email, hashed_password=hashed_password, name=name)
            session.add(user)
            await session.flush()
            return {"id": user.id, "email": user.email, "name": user.name}


async def get_user_by_email(email: str) -> dict | None:
    from app.db.models import User
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT id, email, hashed_password, name FROM users WHERE email = :email"),
            {"email": email},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None


async def list_user_documents(user_id: str) -> list[dict]:
    """Return one row per uploaded document for this user — doc_id, filename, chunk count, upload time."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT doc_id, filename,
                       COUNT(*) FILTER (WHERE chunk_type = 'child') AS chunk_count,
                       MIN(created_at) AS uploaded_at
                FROM document_chunks
                WHERE user_id = :uid
                GROUP BY doc_id, filename
                ORDER BY MIN(created_at) DESC
            """),
            {"uid": user_id},
        )
        return [dict(r._mapping) for r in result.fetchall()]
 
 
async def delete_document(doc_id: str, user_id: str) -> bool:
    """Delete all chunks for a doc. Returns True if anything was deleted."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                text("""
                    DELETE FROM document_chunks
                    WHERE doc_id = :did AND user_id = :uid
                """),
                {"did": doc_id, "uid": user_id},
            )
            return result.rowcount > 0
 
import uuid

from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False, unique=True, index=True)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(String, nullable=False, index=True)
    # Owns this document — every query/ingest scopes to this column.
    # Without it, any authenticated user could read any other user's
    # uploaded documents — the multi-tenancy gap from the code review.
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    chunk_type = Column(String, default="child")
    parent_id = Column(Integer, nullable=True)
    text = Column(Text, nullable=False)
    embedding = Column(Vector(384), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

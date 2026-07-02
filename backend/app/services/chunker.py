"""
Chunker — updated chunk sizes for legal documents.

Only change from original: parent_size 1500→2000, child_size 200→300, overlap 30→50.

Why for legal docs specifically:
  - Legal clauses are long (200-600 words). child_size=200 was cutting
    mid-clause, splitting "shall not be liable for... [cut] ...any indirect damages"
    into two meaningless fragments.
  - child_size=300 keeps most sub-clauses intact.
  - parent_size=2000 captures a full contract section (e.g. "Limitation of Liability")
    including its sub-clauses — the LLM gets the full legal context.
  - overlap=50 prevents sentence boundary cuts at chunk edges.

The retrieval flow:
  child chunk → vector search finds it (small = precise match)
  parent chunk → LLM reads it (large = full legal context)
"""
from pypdf import PdfReader
from docx import Document
from bs4 import BeautifulSoup
import markdown, json, csv, io

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".docx", ".md", ".html", ".htm", ".csv", ".json"}
SEPARATORS = ["\n\n\n", "\n\n", "\n", ". ", " "]


def extract_text(file_bytes: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(file_bytes))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    elif name.endswith(".docx"):
        doc = Document(io.BytesIO(file_bytes))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    elif name.endswith(".md"):
        html = markdown.markdown(file_bytes.decode("utf-8", errors="ignore"))
        return BeautifulSoup(html, "html.parser").get_text(separator="\n\n")
    elif name.endswith((".html", ".htm")):
        return BeautifulSoup(
            file_bytes.decode("utf-8", errors="ignore"), "html.parser"
        ).get_text(separator="\n\n")
    elif name.endswith(".csv"):
        text = file_bytes.decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(text))
        return "\n\n".join(
            " | ".join(f"{k}: {v}" for k, v in row.items()) for row in reader
        )
    elif name.endswith(".json"):
        try:
            return json.dumps(
                json.loads(file_bytes.decode("utf-8", errors="ignore")), indent=2
            )
        except json.JSONDecodeError:
            return file_bytes.decode("utf-8", errors="ignore")
    return file_bytes.decode("utf-8", errors="ignore")


def _split_by_separator(text: str, sep: str) -> list[str]:
    if sep == " ":
        return text.split()
    return [p.strip() for p in text.split(sep) if p.strip()]


def recursive_chunk(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    separators: list[str] = None,
) -> list[str]:
    if separators is None:
        separators = SEPARATORS
    sep = separators[0]
    rest = separators[1:]
    splits = _split_by_separator(text, sep)
    chunks, current = [], []
    for split in splits:
        words = split.split()
        if len(words) > chunk_size and rest:
            if current:
                chunks.append(" ".join(current))
                current = []
            chunks.extend(recursive_chunk(split, chunk_size, chunk_overlap, rest))
            continue
        if len(current) + len(words) > chunk_size:
            if current:
                chunks.append(" ".join(current))
                current = current[-chunk_overlap:]
        current.extend(words)
    if current:
        chunks.append(" ".join(current))
    return [c for c in chunks if c.strip()]


def build_parent_child_chunks(
    text: str,
    parent_size: int = 2000,   # ← updated for legal docs (was 1500)
    child_size: int = 300,     # ← updated for legal docs (was 200)
    overlap: int = 50,         # ← updated for legal docs (was 30)
) -> list[dict]:
    """
    Two-level chunking:
      Parent chunks — large, sent to LLM as context (full clause/section)
      Child chunks  — small, used for vector search (precise matching)

    During query:
      1. Vector search finds the right child chunk
      2. System fetches its parent for full context
      3. LLM reads the parent — gets complete legal meaning
    """
    parents = recursive_chunk(text, chunk_size=parent_size, chunk_overlap=0)
    result = []
    for p_idx, parent_text in enumerate(parents):
        result.append({
            "chunk_type": "parent",
            "chunk_index": p_idx,
            "text": parent_text,
        })
        children = recursive_chunk(parent_text, chunk_size=child_size, chunk_overlap=overlap)
        for c_idx, child_text in enumerate(children):
            result.append({
                "chunk_type": "child",
                "chunk_index": p_idx * 1000 + c_idx,
                "parent_chunk_index": p_idx,
                "text": child_text,
            })
    return result

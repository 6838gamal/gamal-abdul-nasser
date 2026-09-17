# app/services/vector_ops.py
import json
from typing import Sequence
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.vector_mode import is_pgvector


async def insert_chunk(
    db: AsyncSession,
    *,
    source_type: str,
    source_id: int,
    chunk_index: int,
    title: str,
    content: str,
    content_hash: str,
    meta: dict,
    embedding: list[float],
):
    """إدراج chunk — يعمل مع vector و jsonb."""
    if is_pgvector():
        await db.execute(text("""
            INSERT INTO knowledge_chunks
              (source_type, source_id, chunk_index, title, content,
               content_hash, metadata, embedding)
            VALUES
              (:st, :si, :ci, :ti, :co, :ch, :meta, CAST(:emb AS vector))
        """), {
            "st": source_type, "si": source_id, "ci": chunk_index,
            "ti": title, "co": content, "ch": content_hash,
            "meta": json.dumps(meta),
            "emb": str(embedding),   # "[0.1, 0.2, ...]"
        })
    else:
        await db.execute(text("""
            INSERT INTO knowledge_chunks
              (source_type, source_id, chunk_index, title, content,
               content_hash, metadata, embedding)
            VALUES
              (:st, :si, :ci, :ti, :co, :ch, :meta, CAST(:emb AS jsonb))
        """), {
            "st": source_type, "si": source_id, "ci": chunk_index,
            "ti": title, "co": content, "ch": content_hash,
            "meta": json.dumps(meta),
            "emb": json.dumps(embedding),
        })


async def search_similar(
    db: AsyncSession,
    query_embedding: list[float],
    *,
    top_k: int = 20,
    source_types: list[str] | None = None,
) -> list[dict]:
    """بحث دلالي — يعمل مع vector و jsonb."""
    if is_pgvector():
        return await _search_pgvector(db, query_embedding, top_k, source_types)
    return await _search_jsonb(db, query_embedding, top_k, source_types)


async def _search_pgvector(db, emb, top_k, source_types):
    sql = """
        SELECT id, source_type, source_id, title, content, metadata,
               1 - (embedding <=> CAST(:emb AS vector)) AS score
        FROM knowledge_chunks
        WHERE 1=1
    """
    params = {"emb": str(emb), "k": top_k}
    if source_types:
        sql += " AND source_type = ANY(:st)"
        params["st"] = source_types
    sql += " ORDER BY embedding <=> CAST(:emb AS vector) LIMIT :k"

    rows = (await db.execute(text(sql), params)).mappings().all()
    return [dict(r) for r in rows]


async def _search_jsonb(db, emb, top_k, source_types):
    """بحث Python — للقواعد الصغيرة فقط."""
    sql = "SELECT id, source_type, source_id, title, content, metadata, embedding FROM knowledge_chunks WHERE 1=1"
    params = {}
    if source_types:
        sql += " AND source_type = ANY(:st)"
        params["st"] = source_types

    rows = (await db.execute(text(sql), params)).mappings().all()

    # حساب cosine similarity يدوياً
    import math
    q_norm = math.sqrt(sum(x * x for x in emb))

    scored = []
    for r in rows:
        v = r["embedding"]
        if isinstance(v, str):
            v = json.loads(v)
        dot = sum(a * b for a, b in zip(emb, v))
        v_norm = math.sqrt(sum(x * x for x in v))
        score = dot / (q_norm * v_norm + 1e-9)
        scored.append({**dict(r), "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]

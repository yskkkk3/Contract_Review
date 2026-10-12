"""Qdrant loader: write dense vectors with payload metadata (dense path of hybrid RAG)."""
import hashlib
import json
from contextlib import suppress
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings
from app.rag.client import get_sf_client
from app.rag.ingest.chunker import Chunk

settings = get_settings()


def _point_id(doc_id: str, text: str, section: str = "") -> str:
    """Stable content identity: corpus order and batch size must not create duplicate points."""
    identity = json.dumps([doc_id, section, text], ensure_ascii=False, separators=(",", ":"))
    return str(UUID(hex=hashlib.md5(identity.encode()).hexdigest()))


async def ensure_collection(client: AsyncQdrantClient, collection: str, vector_size: int = 1024) -> None:
    exists = await client.collection_exists(collection)
    if not exists:
        await client.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )
    # 元数据过滤索引（幂等：已存在时忽略错误）
    for field in ("doc_type", "source"):
        with suppress(Exception):
            await client.create_payload_index(
                collection_name=collection,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )


async def upsert_chunks(client: AsyncQdrantClient, collection: str, chunks: list[Chunk], batch_size: int = 10) -> int:
    """批量 embedding + upsert。返回写入点数。

    百炼 text-embedding-v4 单次最多接受 10 条文本，因此默认批次不能超过 10。
    """
    sf = get_sf_client()
    count = 0
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        vectors = await sf.embed([c.text for c in batch])
        points = [
            models.PointStruct(
                id=_point_id(c.doc_id, c.text, c.section),
                vector=vectors[j],
                payload={
                    "doc_id": c.doc_id,
                    "text": c.text,
                    "source": c.source,
                    "doc_type": c.doc_type,
                    "section": c.section,
                    **c.meta,
                    "meta": c.meta,
                },
            )
            for j, c in enumerate(batch)
        ]
        await client.upsert(collection_name=collection, points=points)
        count += len(points)
    return count

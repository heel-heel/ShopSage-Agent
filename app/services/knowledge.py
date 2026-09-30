"""A small Chroma-backed knowledge layer with a deterministic local fallback."""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any

from app.config import get_settings


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]{1,3}", text.lower()))


def _embedding(text: str, dimensions: int = 96) -> list[float]:
    vector = [0.0] * dimensions
    for token in _tokens(text):
        index = int(hashlib.sha256(token.encode()).hexdigest(), 16) % dimensions
        vector[index] += 1.0
    magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / magnitude for value in vector]


class KnowledgeStore:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.collection = None
        try:
            import chromadb

            settings = get_settings()
            if settings.chroma_host:
                client = chromadb.HttpClient(host=settings.chroma_host, port=8000)
            else:
                Path(settings.chroma_path).mkdir(parents=True, exist_ok=True)
                client = chromadb.PersistentClient(path=settings.chroma_path)
            self.collection = client.get_or_create_collection(
                name="coffee_knowledge", metadata={"hnsw:space": "cosine"}
            )
        except Exception:
            # The application stays runnable without a vector runtime in local demos.
            self.collection = None

    def upsert(self, item_id: str, title: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        record = {"id": item_id, "title": title, "text": text, "metadata": metadata or {}}
        self.items[item_id] = record
        if self.collection:
            safe_metadata = {key: str(value) for key, value in record["metadata"].items() if value is not None}
            safe_metadata["title"] = title
            self.collection.upsert(
                ids=[item_id],
                documents=[text],
                metadatas=[safe_metadata],
                embeddings=[_embedding(f"{title} {text}")],
            )

    def query(self, question: str, limit: int = 4) -> list[dict[str, Any]]:
        if self.collection and self.items:
            result = self.collection.query(query_embeddings=[_embedding(question)], n_results=min(limit, len(self.items)))
            ids = result.get("ids", [[]])[0]
            return [self.items[item_id] for item_id in ids if item_id in self.items]

        query_tokens = _tokens(question)
        scored = []
        for record in self.items.values():
            overlap = len(query_tokens & _tokens(f"{record['title']} {record['text']}"))
            scored.append((overlap, record))
        return [record for _, record in sorted(scored, key=lambda pair: pair[0], reverse=True)[:limit]]


knowledge_store = KnowledgeStore()

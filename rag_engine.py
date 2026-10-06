"""Retrieval: embeds knowledge_base files into ChromaDB and searches them."""
from pathlib import Path

import chromadb

from report_parser import extract_text_from_file
from utils import CHROMA_DIR, EMBED_MODEL, KB_DIR, chunk_text, get_logger

log = get_logger(__name__)
SUPPORTED = {".txt", ".md", ".pdf"}


class RAGEngine:
    def __init__(self) -> None:
        self._embedder = None
        self._client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.collection = self._client.get_or_create_collection(
            "health_kb", metadata={"hnsw:space": "cosine"})

    @property
    def embedder(self):
        if self._embedder is None:  # lazy: model is large, load once
            from sentence_transformers import SentenceTransformer
            log.info("Loading embedding model %s", EMBED_MODEL)
            self._embedder = SentenceTransformer(EMBED_MODEL)
        return self._embedder

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return self.embedder.encode(texts, normalize_embeddings=True).tolist()

    def ingest(self) -> int:
        """Index every file in knowledge_base/. Safe to run repeatedly (upsert)."""
        total = 0
        for path in sorted(Path(KB_DIR).glob("*")):
            if path.suffix.lower() not in SUPPORTED:
                continue
            try:
                text = extract_text_from_file(path.read_bytes(), path.name)
            except Exception as e:
                log.warning("Skipping %s: %s", path.name, e)
                continue
            chunks = chunk_text(text)
            if not chunks:
                continue
            self.collection.upsert(
                ids=[f"{path.name}-{i}" for i in range(len(chunks))],
                documents=chunks,
                embeddings=self._embed(chunks),
                metadatas=[{"source": path.name, "chunk": i} for i in range(len(chunks))],
            )
            total += len(chunks)
        log.info("Indexed %d chunks", total)
        return total

    def count(self) -> int:
        return self.collection.count()

    def query(self, question: str, k: int = 4, max_distance: float = 0.75) -> list[dict]:
        n = self.collection.count()
        if n == 0:
            return []
        res = self.collection.query(query_embeddings=self._embed([question]),
                                    n_results=min(k, n))
        out = []
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
            if dist <= max_distance:
                out.append({"text": doc, "source": meta.get("source", "?"), "distance": dist})
        return out
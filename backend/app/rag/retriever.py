from __future__ import annotations

import logging

from app.core.config import settings
from app.rag.simple_embed import tokenize

from .embeddings import available_embedder
from .store import VectorStore

logger = logging.getLogger(__name__)

DEFAULT_MIN_SCORES = {
    'fastembed': 0.30,
    'hash': 0.05,
}


class Retriever:
    def __init__(self) -> None:
        self.store = VectorStore(settings.vector_dir)
        self.loaded = self.store.load()
        self.embedder = None
        if self.loaded:
            provider = self.store.manifest.get('provider')
            try:
                self.embedder = available_embedder(provider)
            except Exception as exc:
                logger.error('Embedding provider unavailable for retrieval: %s', exc)
                self.embedder = None

    def reload(self) -> bool:
        self.loaded = self.store.load()
        if self.loaded:
            self.embedder = available_embedder(self.store.manifest.get('provider'))
        return self.loaded

    def min_score(self) -> float:
        if settings.rag_min_score is not None:
            return settings.rag_min_score
        provider = self.store.manifest.get('provider') or 'hash'
        return DEFAULT_MIN_SCORES.get(provider, 0.2)

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        source_filter: str | None = None,
    ) -> list[dict]:
        if not self.loaded or self.embedder is None or not query.strip():
            return []
        limit = top_k or settings.top_k_results
        query_vector = self.embedder.embed_query(query)
        candidates = self.store.search(query_vector, top_k=max(limit * 6, 24), source_filter=source_filter)
        if not candidates:
            return []
        query_terms = set(tokenize(query))
        threshold = self.min_score()
        ranked: list[dict] = []
        for candidate in candidates:
            vector_score = float(candidate.get('vector_score') or 0.0)
            text = f"{candidate.get('title', '')} {candidate.get('content', '')}"
            text_terms = set(tokenize(text))
            overlap = len(query_terms & text_terms) / max(1, len(query_terms))
            if vector_score < threshold and overlap < 0.5:
                continue
            candidate['lexical_overlap'] = round(overlap, 4)
            candidate['score'] = round(0.8 * vector_score + 0.2 * overlap, 4)
            ranked.append(candidate)
        ranked.sort(key=lambda item: item['score'], reverse=True)

        per_url: dict[str, int] = {}
        selected: list[dict] = []
        for candidate in ranked:
            url = candidate.get('url') or ''
            if per_url.get(url, 0) >= settings.rag_max_chunks_per_url:
                continue
            per_url[url] = per_url.get(url, 0) + 1
            selected.append(candidate)
            if len(selected) >= limit:
                break
        return selected

    def keyword_search(self, query: str, top_k: int = 5, source_filter: str | None = None) -> list[dict]:
        terms = [term for term in tokenize(query) if len(term) > 2]
        if not terms:
            return []
        matches: list[dict] = []
        for metadata in self.store.metadatas:
            if source_filter and source_filter != 'all' and metadata.get('source') != source_filter:
                continue
            haystack = f"{metadata.get('title', '')} {metadata.get('content', '')}".lower()
            hits = sum(1 for term in terms if term in haystack)
            if hits == 0:
                continue
            metadata = dict(metadata)
            metadata['score'] = hits / len(terms)
            metadata['vector_score'] = 0.0
            metadata['lexical_overlap'] = metadata['score']
            matches.append(metadata)
        matches.sort(key=lambda item: item['score'], reverse=True)
        return matches[:top_k]


_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever


def reset_retriever() -> None:
    global _retriever
    _retriever = None

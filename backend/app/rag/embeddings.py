from __future__ import annotations

import logging
from typing import Protocol

import numpy as np

from app.core.config import settings

from .simple_embed import embed_texts as hashed_embed_texts

logger = logging.getLogger(__name__)

HASH_PROVIDER = 'hash'
FASTEMBED_PROVIDER = 'fastembed'
HASH_DIM = 384


class Embedder(Protocol):
    provider: str
    model_name: str
    dim: int

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


class HashedEmbedder:
    provider = HASH_PROVIDER
    model_name = 'hashed-tf-384'
    dim = HASH_DIM

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return hashed_embed_texts(texts, dim=self.dim)

    def embed_query(self, text: str) -> np.ndarray:
        return hashed_embed_texts([text], dim=self.dim)[0]


class FastEmbedder:
    provider = FASTEMBED_PROVIDER

    def __init__(self, model_name: str, cache_dir: str, threads: int) -> None:
        from fastembed import TextEmbedding

        self.model_name = model_name
        self.dim = 384
        self._model = TextEmbedding(
            model_name=model_name,
            cache_dir=cache_dir,
            threads=threads,
        )

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype='float32')
        vectors = [np.asarray(vector, dtype='float32') for vector in self._model.embed(texts)]
        if vectors:
            self.dim = len(vectors[0])
        return np.vstack(vectors)

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]


_cache: dict[str, Embedder] = {}


def get_embedder(provider: str | None = None) -> Embedder:
    requested = (provider or settings.embedding_provider or 'auto').strip().lower()
    if requested in ('hash', 'hashed', 'simple', 'tfidf'):
        key = HASH_PROVIDER
        if key not in _cache:
            _cache[key] = HashedEmbedder()
        return _cache[key]

    key = FASTEMBED_PROVIDER
    if key in _cache:
        return _cache[key]

    try:
        settings.embedding_cache_path.mkdir(parents=True, exist_ok=True)
        embedder = FastEmbedder(
            model_name=settings.embedding_model,
            cache_dir=str(settings.embedding_cache_path),
            threads=settings.embedding_threads,
        )
        _cache[key] = embedder
        logger.info('Using fastembed model %s', settings.embedding_model)
        return embedder
    except Exception as exc:
        if requested == FASTEMBED_PROVIDER:
            logger.error('FastEmbed requested but unavailable: %s', exc)
            raise
        logger.warning('FastEmbed unavailable, using hashed embeddings: %s', exc)
        _cache[key] = HashedEmbedder()
        return _cache[key]


def available_embedder(preferred: str | None = None) -> Embedder:
    if preferred == HASH_PROVIDER:
        return get_embedder(HASH_PROVIDER)
    if preferred == FASTEMBED_PROVIDER:
        try:
            return get_embedder(FASTEMBED_PROVIDER)
        except Exception:
            return get_embedder(HASH_PROVIDER)
    return get_embedder()

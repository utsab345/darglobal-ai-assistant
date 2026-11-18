from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.embeddings: np.ndarray | None = None
        self.metadatas: list[dict[str, Any]] = []
        self.manifest: dict[str, Any] = {}
        self.index = None
        self.backend = 'numpy'
        self.directory.mkdir(parents=True, exist_ok=True)

    @property
    def embeddings_path(self) -> Path:
        return self.directory / 'embeddings.npy'

    @property
    def metadata_path(self) -> Path:
        return self.directory / 'metadata.json'

    @property
    def manifest_path(self) -> Path:
        return self.directory / 'manifest.json'

    @property
    def index_path(self) -> Path:
        return self.directory / 'index.faiss'

    def normalize(self, array: np.ndarray) -> np.ndarray:
        values = np.asarray(array, dtype='float32')
        if values.ndim == 1:
            norm = np.linalg.norm(values) or 1.0
            return values / norm
        norms = np.linalg.norm(values, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return values / norms

    def build(
        self,
        embeddings: np.ndarray,
        metadatas: list[dict[str, Any]],
        provider: str,
        model_name: str,
    ) -> None:
        matrix = self.normalize(embeddings)
        self.embeddings = matrix
        self.metadatas = metadatas
        self.manifest = {
            'provider': provider,
            'model': model_name,
            'dim': int(matrix.shape[1]) if matrix.size else 0,
            'count': len(metadatas),
            'built_at': datetime.now(timezone.utc).isoformat(),
            'backend': 'numpy',
        }
        self.index = None
        try:
            import faiss

            index = faiss.IndexFlatIP(matrix.shape[1])
            index.add(matrix)
            self.index = index
            self.manifest['backend'] = 'faiss'
            self.backend = 'faiss'
        except Exception as exc:
            logger.info('FAISS unavailable, using numpy index: %s', exc)
            self.backend = 'numpy'
        self.save()

    def save(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.embeddings is not None:
            np.save(self.embeddings_path, self.embeddings)
        metadata_tmp = self.metadata_path.with_suffix('.json.tmp')
        metadata_tmp.write_text(json.dumps(self.metadatas, ensure_ascii=False), encoding='utf-8')
        metadata_tmp.replace(self.metadata_path)
        manifest_tmp = self.manifest_path.with_suffix('.json.tmp')
        manifest_tmp.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        manifest_tmp.replace(self.manifest_path)
        if self.backend == 'faiss' and self.index is not None:
            try:
                import faiss

                faiss.write_index(self.index, str(self.index_path))
            except Exception:
                self.backend = 'numpy'
                self.manifest['backend'] = 'numpy'

    def load(self) -> bool:
        if not self.metadata_path.exists() or not self.embeddings_path.exists():
            return False
        try:
            self.metadatas = json.loads(self.metadata_path.read_text(encoding='utf-8'))
            self.embeddings = np.load(self.embeddings_path)
        except (OSError, ValueError):
            return False
        if self.manifest_path.exists():
            try:
                self.manifest = json.loads(self.manifest_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                self.manifest = {}
        self.index = None
        self.backend = 'numpy'
        if self.manifest.get('backend') == 'faiss' and self.index_path.exists():
            try:
                import faiss

                self.index = faiss.read_index(str(self.index_path))
                self.backend = 'faiss'
            except Exception:
                self.index = None
                self.backend = 'numpy'
        return True

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        source_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.embeddings is None or len(self.metadatas) == 0:
            return []
        query = self.normalize(np.asarray(query_embedding, dtype='float32')).reshape(1, -1)
        if query.shape[1] != self.embeddings.shape[1]:
            logger.warning('Embedding dimension mismatch: query=%s index=%s', query.shape[1], self.embeddings.shape[1])
            return []
        count = len(self.metadatas)
        fetch_k = min(max(top_k * 8, top_k), count)
        pairs: list[tuple[float, int]]
        if self.backend == 'faiss' and self.index is not None:
            try:
                scores, indexes = self.index.search(query, fetch_k)
                pairs = [(float(score), int(index)) for score, index in zip(scores[0], indexes[0]) if index >= 0]
            except Exception:
                pairs = self._numpy_search(query, fetch_k)
        else:
            pairs = self._numpy_search(query, fetch_k)

        results: list[dict[str, Any]] = []
        for score, index in pairs:
            if index < 0 or index >= count:
                continue
            metadata = dict(self.metadatas[index])
            if source_filter and source_filter != 'all' and metadata.get('source') != source_filter:
                continue
            metadata['vector_score'] = score
            metadata['score'] = score
            results.append(metadata)
            if len(results) >= top_k:
                break
        return results

    def _numpy_search(self, query: np.ndarray, fetch_k: int) -> list[tuple[float, int]]:
        if self.embeddings is None or len(self.embeddings) == 0:
            return []
        similarities = np.dot(self.embeddings, query[0])
        indexes = np.argsort(-similarities)[:fetch_k]
        return [(float(similarities[index]), int(index)) for index in indexes]

    @property
    def size(self) -> int:
        return len(self.metadatas)

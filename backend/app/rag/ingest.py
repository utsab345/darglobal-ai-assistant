from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.utils.text import chunk_text, clean_text, content_hash, make_id, normalize_block

from .embeddings import available_embedder
from .store import VectorStore

logger = logging.getLogger(__name__)

RAW_SUFFIX_BLOCKLIST = ('last_scrape_stats.json', 'last_scrape_summary.json')


def load_raw_documents() -> list[dict]:
    documents: list[dict] = []
    raw_dir = settings.raw_data_dir
    if not raw_dir.exists():
        return documents
    for path in sorted(raw_dir.rglob('*.json')):
        if path.name in RAW_SUFFIX_BLOCKLIST:
            continue
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            logger.warning('Could not read raw document %s: %s', path, exc)
            continue
        if isinstance(payload, dict) and payload.get('content'):
            documents.append(payload)
    return documents


def normalize_document(document: dict) -> dict:
    metadata = document.get('metadata') or {}
    source = document.get('source') or 'unknown'
    site = metadata.get('site') or ('DarGlobal' if source == 'dar_global' else 'Wasalt' if source == 'wasalt' else 'Unknown')
    return {
        'id': document.get('id') or make_id(str(document.get('url', ''))),
        'source': source,
        'url': document.get('url', ''),
        'title': normalize_block(document.get('title', '')),
        'content': clean_text(document.get('content', '')),
        'scraped_at': document.get('scraped_at'),
        'metadata': {
            'site': site,
            'source_label': metadata.get('source_label') or site,
            'project_name': metadata.get('project_name'),
            'description_meta': metadata.get('description_meta'),
            'location': metadata.get('location'),
            'country': metadata.get('country'),
            'property_type': metadata.get('property_type'),
            'price': metadata.get('price'),
            'bedrooms': metadata.get('bedrooms'),
            'area_sqm': metadata.get('area_sqm'),
            'status': metadata.get('status'),
            'amenities': metadata.get('amenities') or [],
            'contact_info': metadata.get('contact_info') or {},
            'page_path': metadata.get('page_path'),
            'listing_id': metadata.get('listing_id'),
            'language': metadata.get('language') or 'en',
        },
    }


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def build_knowledge_base() -> dict:
    settings.processed_data_dir.mkdir(parents=True, exist_ok=True)
    settings.vector_dir.mkdir(parents=True, exist_ok=True)

    raw_documents = load_raw_documents()
    by_url: dict[str, dict] = {}
    for raw in raw_documents:
        document = normalize_document(raw)
        if not document['url'] or len(document['content']) < 80:
            continue
        previous = by_url.get(document['url'])
        if previous is None or len(document['content']) > len(previous['content']):
            by_url[document['url']] = document

    by_hash: dict[str, dict] = {}
    for document in by_url.values():
        digest = content_hash(document['content'])
        if digest in by_hash:
            continue
        by_hash[digest] = document
    documents = list(by_hash.values())

    _write_json(settings.processed_data_dir / 'documents.json', documents)

    chunks: list[dict] = []
    texts: list[str] = []
    for document in documents:
        parts = chunk_text(document['content'], settings.chunk_size, settings.chunk_overlap)
        total = len(parts)
        for index, part in enumerate(parts):
            metadata = dict(document['metadata'])
            metadata.update(
                {
                    'chunk_index': index,
                    'total_chunks': total,
                    'scraped_at': document.get('scraped_at'),
                }
            )
            chunks.append(
                {
                    'chunk_id': f'{document["id"]}:{index}',
                    'doc_id': document['id'],
                    'source': document['source'],
                    'url': document['url'],
                    'title': document['title'],
                    'content': part,
                    'snippet': part[:320],
                    'scraped_at': document.get('scraped_at'),
                    'metadata': metadata,
                }
            )
            prefix = ' '.join(
                part
                for part in (
                    document['title'],
                    metadata.get('location') or '',
                    metadata.get('property_type') or '',
                )
                if part
            )
            texts.append(f'{prefix}\n{part}'.strip())

    embedder = available_embedder()
    store = VectorStore(settings.vector_dir)
    if texts:
        embeddings = embedder.embed_documents(texts)
        store.build(embeddings, chunks, provider=embedder.provider, model_name=embedder.model_name)
    else:
        store.build(embedder.embed_documents([''])[:0], [], provider=embedder.provider, model_name=embedder.model_name)

    stats = {
        'built_at': datetime.now(timezone.utc).isoformat(),
        'raw_documents_loaded': len(raw_documents),
        'unique_documents': len(documents),
        'duplicates_removed': len(by_url) - len(documents),
        'chunks': len(chunks),
        'sources': {
            'dar_global': sum(1 for document in documents if document['source'] == 'dar_global'),
            'wasalt': sum(1 for document in documents if document['source'] == 'wasalt'),
        },
        'chunks_by_source': {
            'dar_global': sum(1 for chunk in chunks if chunk['source'] == 'dar_global'),
            'wasalt': sum(1 for chunk in chunks if chunk['source'] == 'wasalt'),
        },
        'embedding_provider': embedder.provider,
        'embedding_model': embedder.model_name,
        'embedding_dim': int(store.embeddings.shape[1]) if store.embeddings is not None and store.embeddings.size else 0,
        'vector_backend': store.manifest.get('backend', 'numpy'),
        'last_scrape_at': _last_scrape_at(documents),
    }
    _write_json(settings.processed_data_dir / 'kb_stats.json', stats)
    logger.info(
        'Knowledge base built: %s documents, %s chunks, provider=%s',
        stats['unique_documents'],
        stats['chunks'],
        stats['embedding_provider'],
    )
    return stats


def _last_scrape_at(documents: list[dict]) -> str | None:
    timestamps = [document.get('scraped_at') for document in documents if document.get('scraped_at')]
    return max(timestamps) if timestamps else None


def get_kb_stats() -> dict:
    path = settings.processed_data_dir / 'kb_stats.json'
    if path.exists():
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    return {
        'built_at': None,
        'raw_documents_loaded': 0,
        'unique_documents': 0,
        'chunks': 0,
        'sources': {'dar_global': 0, 'wasalt': 0},
        'chunks_by_source': {'dar_global': 0, 'wasalt': 0},
        'embedding_provider': None,
        'embedding_model': None,
        'embedding_dim': 0,
        'vector_backend': None,
        'last_scrape_at': None,
    }


def ensure_knowledge_base(force: bool = False) -> dict:
    if not settings.auto_build_kb and not force:
        return get_kb_stats()
    stats = get_kb_stats()
    manifest_path = settings.vector_dir / 'manifest.json'
    manifest: dict = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            manifest = {}
    try:
        embedder = available_embedder(manifest.get('provider'))
        provider = embedder.provider
    except Exception:
        provider = 'hash'
    raw_count = len(load_raw_documents())
    needs_build = (
        force
        or not manifest
        or stats.get('chunks', 0) == 0
        or stats.get('embedding_provider') != provider
        or stats.get('raw_documents_loaded') != raw_count
    )
    if needs_build:
        return build_knowledge_base()
    return stats

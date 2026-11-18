from __future__ import annotations

import asyncio
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.models.schemas import ChatRequest, ChatResponse, HealthResponse, ScrapeRequest
from app.rag.ingest import build_knowledge_base, get_kb_stats, load_raw_documents
from app.rag.retriever import reset_retriever
from app.scraping.service import get_scrape_stats, run_scrape
from app.services.chat import generate_chat_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api')
limiter = Limiter(key_func=get_remote_address)


def _document_items() -> list[dict]:
    documents = load_raw_documents()
    items: list[dict] = []
    seen: set[str] = set()
    for document in documents:
        url = document.get('url')
        if not url or url in seen:
            continue
        seen.add(url)
        metadata = document.get('metadata') or {}
        items.append(
            {
                'id': document.get('id'),
                'title': document.get('title') or url,
                'url': url,
                'source': document.get('source'),
                'source_label': metadata.get('source_label')
                or ('DarGlobal' if document.get('source') == 'dar_global' else 'Wasalt'),
                'scraped_at': document.get('scraped_at'),
                'metadata': metadata,
            }
        )
    return items


@router.get('/stats')
async def stats() -> dict:
    kb = get_kb_stats()
    scrape = get_scrape_stats()
    documents = _document_items()
    return {
        'scrape': scrape,
        'knowledge_base': kb,
        'sources': {
            'dar_global': {
                'label': 'DarGlobal',
                'documents': sum(1 for item in documents if item['source'] == 'dar_global'),
                'chunks': (kb.get('chunks_by_source') or {}).get('dar_global', 0),
                'website': 'https://darglobal.co.uk/',
            },
            'wasalt': {
                'label': 'Wasalt',
                'documents': sum(1 for item in documents if item['source'] == 'wasalt'),
                'chunks': (kb.get('chunks_by_source') or {}).get('wasalt', 0),
                'website': 'https://wasalt.sa/',
            },
        },
        'embedding': {
            'provider': kb.get('embedding_provider'),
            'model': kb.get('embedding_model'),
            'dimension': kb.get('embedding_dim'),
            'vector_backend': kb.get('vector_backend'),
        },
        'openrouter': {
            'configured': settings.openrouter_configured,
            'model_setting': settings.openrouter_model,
        },
    }


@router.get('/sources')
async def sources(
    source: str = Query(default='all', pattern='^(all|dar_global|wasalt)$'),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    items = _document_items()
    if source != 'all':
        items = [item for item in items if item['source'] == source]
    items.sort(key=lambda item: (item['source'] or '', item['title'] or ''))
    return {'count': len(items), 'returned': min(limit, len(items)), 'sources': items[:limit]}


@router.get('/projects')
async def projects(
    source: str = Query(default='all', pattern='^(all|dar_global|wasalt)$'),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    items = _document_items()
    if source != 'all':
        items = [item for item in items if item['source'] == source]
    projects: list[dict] = []
    for item in items:
        metadata = item.get('metadata') or {}
        name = metadata.get('project_name') or item.get('title')
        if not name:
            continue
        projects.append(
            {
                'id': item.get('id'),
                'name': name,
                'source': item.get('source'),
                'source_label': item.get('source_label'),
                'url': item.get('url'),
                'location': metadata.get('location'),
                'country': metadata.get('country'),
                'property_type': metadata.get('property_type'),
                'description': metadata.get('description_meta')
                or (item.get('metadata', {}).get('project_name') or ''),
                'price': metadata.get('price'),
                'bedrooms': metadata.get('bedrooms'),
                'area_sqm': metadata.get('area_sqm'),
                'amenities': metadata.get('amenities') or [],
                'status': metadata.get('status'),
                'scraped_at': item.get('scraped_at'),
            }
        )
    deduped: dict[str, dict] = {}
    for project in projects:
        deduped[project['url']] = project
    values = sorted(deduped.values(), key=lambda project: (project['source'] or '', project['name'] or ''))
    return {'count': len(values), 'returned': min(limit, len(values)), 'projects': values[:limit]}


@router.post('/chat', response_model=ChatResponse)
@limiter.limit(settings.rate_limit_chat)
async def chat(request: Request, payload: ChatRequest) -> ChatResponse:
    return await generate_chat_response(payload)


@router.post('/scrape')
@limiter.limit(settings.rate_limit_scrape)
async def scrape(
    request: Request,
    payload: ScrapeRequest,
    x_admin_token: str | None = Header(default=None, alias='X-Admin-Token'),
) -> dict:
    if not settings.scrape_admin_token:
        raise HTTPException(status_code=503, detail='Scraping endpoint is disabled because SCRAPE_ADMIN_TOKEN is not configured.')
    if not x_admin_token or not hmac.compare_digest(x_admin_token, settings.scrape_admin_token):
        raise HTTPException(status_code=401, detail='Unauthorized scrape request.')
    results = await asyncio.to_thread(
        run_scrape,
        payload.sites,
        payload.max_pages_per_site,
        True,
    )
    knowledge_base = None
    if payload.rebuild_knowledge_base:
        knowledge_base = await asyncio.to_thread(build_knowledge_base)
        reset_retriever()
    return {'results': results, 'knowledge_base': knowledge_base}


@router.get('/health', response_model=HealthResponse)
async def health() -> HealthResponse:
    kb = get_kb_stats()
    scrape = get_scrape_stats()
    return HealthResponse(
        status='ok',
        version=settings.app_version,
        environment=settings.app_env,
        knowledge_base_ready=kb.get('chunks', 0) > 0,
        documents=kb.get('unique_documents', 0),
        chunks=kb.get('chunks', 0),
        embedding_provider=kb.get('embedding_provider'),
        openrouter_configured=settings.openrouter_configured,
        openrouter_model=settings.openrouter_model,
        last_scrape_at=scrape.get('ran_at') or kb.get('last_scrape_at'),
    )

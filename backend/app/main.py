from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes import limiter, router as api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.models.schemas import HealthResponse
from app.rag.ingest import ensure_knowledge_base, get_kb_stats
from app.rag.retriever import reset_retriever
from app.scraping.service import get_scrape_stats

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        stats = await asyncio.to_thread(ensure_knowledge_base)
        reset_retriever()
        logger.info(
            'Knowledge base ready: %s documents, %s chunks, provider=%s',
            stats.get('unique_documents'),
            stats.get('chunks'),
            stats.get('embedding_provider'),
        )
    except Exception as exc:
        logger.exception('Knowledge base initialization failed: %s', exc)
    yield


app = FastAPI(
    title=settings.app_name,
    description='Retrieval-augmented assistant grounded in public DarGlobal and Wasalt website content.',
    version=settings.app_version,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=800)

origins = settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'] if '*' in origins else origins,
    allow_credentials=False,
    allow_methods=['GET', 'POST', 'OPTIONS'],
    allow_headers=['Content-Type', 'X-Admin-Token'],
)

app.include_router(api_router)


@app.middleware('http')
async def request_logging(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception('Unhandled error on %s %s', request.method, request.url.path)
        raise
    duration_ms = (time.perf_counter() - started) * 1000
    logger.info('%s %s %s %.1fms', request.method, request.url.path, response.status_code, duration_ms)
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={'detail': 'Invalid request', 'errors': exc.errors()})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception('Unhandled application error on %s', request.url.path)
    return JSONResponse(status_code=500, content={'detail': 'Internal server error'})


@app.get('/health', response_model=HealthResponse)
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


static_dir: Path = settings.static_path
if static_dir.exists() and (static_dir / 'index.html').exists():
    if (static_dir / 'assets').exists():
        app.mount('/assets', StaticFiles(directory=static_dir / 'assets'), name='assets')

    @app.get('/', include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(static_dir / 'index.html')

    @app.get('/{full_path:path}', include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        candidate = static_dir / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(static_dir / 'index.html')
else:
    logger.warning('Frontend build not found at %s; running in API-only mode', static_dir)

    @app.get('/', include_in_schema=False)
    async def api_root() -> dict:
        return {
            'name': settings.app_name,
            'version': settings.app_version,
            'docs': '/docs',
            'health': '/health',
            'api': '/api/stats',
        }

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SourceSlug = Literal['dar_global', 'wasalt']
SourceFilter = Literal['all', 'dar_global', 'wasalt']


class ChatMessage(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    conversation_history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    source_filter: SourceFilter = 'all'
    top_k: int | None = Field(default=None, ge=1, le=10)

    @field_validator('question')
    @classmethod
    def validate_question(cls, value: str) -> str:
        cleaned = ' '.join(value.split())
        if not cleaned:
            raise ValueError('question must not be blank')
        return cleaned


class SourceItem(BaseModel):
    title: str
    url: str
    source: Literal['dar_global', 'wasalt', 'unknown']
    snippet: str = ''
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceItem] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    model: str | None = None
    retrieved_count: int = 0
    degraded: bool = False
    notice: str | None = None


class ScrapeRequest(BaseModel):
    sites: list[SourceSlug] = Field(default_factory=lambda: ['dar_global', 'wasalt'])
    max_pages_per_site: int | None = Field(default=None, ge=1, le=250)
    rebuild_knowledge_base: bool = True


class ScrapeSiteResult(BaseModel):
    site: str
    pages_attempted: int = 0
    pages_scraped: int = 0
    documents_saved: int = 0
    documents_skipped: int = 0
    pages_blocked: int = 0
    discovered_urls: int = 0
    errors: list[str] = Field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    coverage_note: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    knowledge_base_ready: bool
    documents: int
    chunks: int
    embedding_provider: str | None = None
    openrouter_configured: bool
    openrouter_model: str
    last_scrape_at: str | None = None

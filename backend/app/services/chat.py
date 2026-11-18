from __future__ import annotations

import logging
import re

from app.core.config import settings
from app.models.schemas import ChatRequest, ChatResponse, SourceItem
from app.rag.retriever import get_retriever

from .openrouter import OpenRouterAuthError, OpenRouterClient, OpenRouterError, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

NO_RESULTS_ANSWER = (
    'I could not find verified information about that in the collected DarGlobal and Wasalt dataset. '
    'The knowledge base only contains pages that were publicly accessible during collection, so some projects, '
    'listings, prices, or availability details may be missing. Try a different project name, city, or source filter.'
)

SOURCE_LABELS = {'dar_global': 'DarGlobal', 'wasalt': 'Wasalt', 'unknown': 'Unknown'}


def build_sources(chunks: list[dict]) -> list[SourceItem]:
    sources: list[SourceItem] = []
    seen: set[str] = set()
    for chunk in chunks:
        url = chunk.get('url') or ''
        if not url or url in seen:
            continue
        seen.add(url)
        source = chunk.get('source') if chunk.get('source') in SOURCE_LABELS else 'unknown'
        metadata = dict(chunk.get('metadata') or {})
        metadata.pop('chunk_index', None)
        metadata.pop('total_chunks', None)
        sources.append(
            SourceItem(
                title=chunk.get('title') or url,
                url=url,
                source=source,
                snippet=(chunk.get('snippet') or chunk.get('content') or '')[:320],
                score=chunk.get('score'),
                metadata=metadata,
            )
        )
    return sources


def format_context(chunks: list[dict]) -> str:
    blocks: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        metadata = chunk.get('metadata') or {}
        label = SOURCE_LABELS.get(chunk.get('source'), 'Unknown')
        facts = [
            f"Location: {metadata.get('location')}" if metadata.get('location') else '',
            f"Property type: {metadata.get('property_type')}" if metadata.get('property_type') else '',
            f"Price: {metadata.get('price')}" if metadata.get('price') else '',
            f"Status: {metadata.get('status')}" if metadata.get('status') else '',
            f"Bedrooms: {metadata.get('bedrooms')}" if metadata.get('bedrooms') is not None else '',
            f"Area: {metadata.get('area_sqm')}" if metadata.get('area_sqm') else '',
        ]
        fact_line = ' | '.join(fact for fact in facts if fact)
        blocks.append(
            f'[S{index}] {label}\n'
            f'Title: {chunk.get("title", "")}\n'
            f'URL: {chunk.get("url", "")}\n'
            f'{fact_line}\n'
            f'Content: {chunk.get("content", "")}'
        )
    return '\n\n---\n\n'.join(blocks)


def build_user_prompt(question: str, context: str) -> str:
    return (
        'Answer the user question using ONLY the retrieved context below. '
        'If the context does not contain enough verified information, say so explicitly instead of guessing. '
        'Separate DarGlobal information from Wasalt information when both appear. '
        'Cite sources inline using the [S#] labels and include the source URL for each cited item. '
        'Never invent prices, locations, specifications, availability, amenities, or contact details. '
        'Provide only the final answer for the user. Do not include a thinking process, analysis steps, or internal reasoning.\n\n'
        f'Retrieved context:\n{context}\n\n'
        f'User question: {question}'
    )


_THINKING_START_RE = re.compile(
    r"(?is)^\s*(here['\u2019]?s\s+(a\s+|the\s+)?thinking process\s*:|thinking process\s*:|let['\u2019]?s\s+think\s*:?)\b"
)


def strip_thinking(text: str) -> str:
    if not text:
        return text
    t = text.strip()

    for marker in (
        r'(?im)^\s*#{1,6}\s*final answer\s*:?\s*$',
        r'(?im)^\s*\*\*final answer\*\*\s*:?\s*',
        r'(?im)^\s*final answer\s*:\s*',
        r'(?im)^\s*answer\s*:\s*',
    ):
        m = re.search(marker, t)
        if m:
            candidate = t[m.end():].strip()
            if len(candidate) >= 20:
                return candidate

    if _THINKING_START_RE.match(t) or re.match(r"(?is)^\s*\d+\.\s+\*\*(analy[sz]e|examine|extract|review)\b", t):
        parts = re.split(r'\n\s*\n', t)
        kept: list[str] = []
        dropping = True
        for part in parts:
            ps = part.strip()
            if not ps:
                continue
            looks_analysis = bool(
                re.match(
                    r"(?is)^(\d+\.|\-|\*|here['\u2019]?s|let['\u2019]?s|i need to|i should|analy[sz]e|examine|extract|review|synthesi[sz]e|check constraints|draft|structure|thinking process)",
                    ps,
                )
            ) and len(ps) < 1400
            if dropping and looks_analysis:
                continue
            dropping = False
            kept.append(ps)
        if kept:
            cleaned = '\n\n'.join(kept).strip()
            if cleaned:
                return cleaned

    return t


def ensure_citations(answer: str, sources: list[SourceItem]) -> str:
    if not sources:
        return answer
    if any(source.url and source.url in answer for source in sources):
        return answer
    lines = ['', 'Sources:']
    for index, source in enumerate(sources, start=1):
        label = SOURCE_LABELS.get(source.source, 'Unknown')
        lines.append(f'- [S{index}] {label}  -  {source.title}  -  {source.url}')
    return answer.rstrip() + '\n'.join(lines)


def degraded_answer(chunks: list[dict], notice: str) -> str:
    lines = [
        'The language model is not available right now, so I cannot generate a synthesized answer. '
        'Here are the relevant excerpts retrieved from the collected dataset:',
        '',
    ]
    for index, chunk in enumerate(chunks, start=1):
        label = SOURCE_LABELS.get(chunk.get('source'), 'Unknown')
        snippet = (chunk.get('content') or '').strip().replace('\n', ' ')
        lines.append(f'[S{index}] {label}  -  {chunk.get("title", "")}')
        lines.append(snippet[:700])
        lines.append(f'Source: {chunk.get("url", "")}')
        lines.append('')
    lines.append(f'Notice: {notice}')
    return '\n'.join(lines).strip()


async def generate_chat_response(request: ChatRequest) -> ChatResponse:
    retriever = get_retriever()
    chunks = retriever.retrieve(
        request.question,
        top_k=request.top_k or settings.top_k_results,
        source_filter=request.source_filter,
    )
    if not chunks and request.source_filter != 'all':
        chunks = retriever.keyword_search(
            request.question,
            top_k=request.top_k or settings.top_k_results,
            source_filter=request.source_filter,
        )
    if not chunks:
        chunks = retriever.keyword_search(
            request.question,
            top_k=request.top_k or settings.top_k_results,
            source_filter=request.source_filter,
        )
    sources = build_sources(chunks)

    if not chunks:
        return ChatResponse(
            answer=NO_RESULTS_ANSWER,
            sources=[],
            source_urls=[],
            model=None,
            retrieved_count=0,
            degraded=False,
            notice='No sufficiently relevant chunks were found in the collected dataset.',
        )

    if not settings.openrouter_configured:
        return ChatResponse(
            answer=degraded_answer(chunks, 'OPENROUTER_API_KEY is not configured on the server.'),
            sources=sources,
            source_urls=[source.url for source in sources],
            model=None,
            retrieved_count=len(chunks),
            degraded=True,
            notice='OpenRouter is not configured; showing retrieved dataset excerpts instead of an AI answer.',
        )

    history = [
        {'role': message.role, 'content': message.content}
        for message in request.conversation_history[-6:]
        if message.role in ('user', 'assistant')
    ]
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        *history,
        {'role': 'user', 'content': build_user_prompt(request.question, format_context(chunks))},
    ]

    client = OpenRouterClient()
    try:
        result = await client.chat(messages)
        cleaned = strip_thinking(result.get('content', ''))
        answer = ensure_citations(cleaned, sources)
        return ChatResponse(
            answer=answer,
            sources=sources,
            source_urls=[source.url for source in sources],
            model=result.get('model'),
            retrieved_count=len(chunks),
            degraded=False,
            notice=None,
        )
    except OpenRouterAuthError as exc:
        logger.error('OpenRouter authentication error: %s', exc)
        return ChatResponse(
            answer=degraded_answer(chunks, str(exc)),
            sources=sources,
            source_urls=[source.url for source in sources],
            model=None,
            retrieved_count=len(chunks),
            degraded=True,
            notice='The configured OpenRouter API key was rejected. Showing retrieved dataset excerpts instead.',
        )
    except OpenRouterError as exc:
        logger.warning('OpenRouter request failed: %s', exc)
        return ChatResponse(
            answer=degraded_answer(chunks, str(exc)),
            sources=sources,
            source_urls=[source.url for source in sources],
            model=None,
            retrieved_count=len(chunks),
            degraded=True,
            notice='The AI model service is temporarily unavailable. Showing retrieved dataset excerpts instead.',
        )
    except Exception as exc:
        logger.exception('Unexpected chat failure')
        return ChatResponse(
            answer=degraded_answer(chunks, f'Unexpected error: {type(exc).__name__}'),
            sources=sources,
            source_urls=[source.url for source in sources],
            model=None,
            retrieved_count=len(chunks),
            degraded=True,
            notice='An unexpected error occurred while generating the answer. Showing retrieved dataset excerpts instead.',
        )

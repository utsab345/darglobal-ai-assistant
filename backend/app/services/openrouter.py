from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are the official-information assistant for DarGlobal and Wasalt. "
    "Answer questions using only the retrieved website information provided in your context. "
    "Do not fabricate property details, prices, availability, amenities, or contact information. "
    "Cite the sources used in your answers. If information is unavailable, clearly state that you could not find verified information in the collected dataset. "
    "Distinguish DarGlobal information from Wasalt information. Be professional, concise, and helpful."
)

PREFERRED_FAMILIES = (
    'gemma',
    'nemotron',
    'ling',
    'ernie',
    'qwen',
    'llama',
    'mistral',
    'deepseek',
    'phi',
    'granite',
)

EXCLUDED_ID_PARTS = (
    'embed',
    'rerank',
    'whisper',
    'tts',
    'audio',
    'image',
    'vision',
    'lyria',
    'clip',
)


class OpenRouterError(RuntimeError):
    pass


class OpenRouterAuthError(OpenRouterError):
    pass


class OpenRouterRateLimitError(OpenRouterError):
    pass


class OpenRouterClient:
    def __init__(self) -> None:
        self.base_url = settings.openrouter_base_url.rstrip('/')
        self.api_key = settings.openrouter_api_key.strip()
        self.configured_model = settings.openrouter_model.strip() or 'auto'
        self._resolved_model: str | None = None
        self._resolved_at = 0.0

    def headers(self, include_auth: bool = True) -> dict[str, str]:
        headers = {
            'Content-Type': 'application/json',
            'HTTP-Referer': settings.openrouter_site_url,
            'X-Title': settings.openrouter_app_name,
        }
        if include_auth and self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        return headers

    async def list_models(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f'{self.base_url}/models', headers=self.headers())
            response.raise_for_status()
            payload = response.json()
        return payload.get('data', [])

    def _rank_free_models(self, models: list[dict[str, Any]]) -> list[str]:
        ranked: list[tuple[float, str]] = []
        for model in models:
            model_id = str(model.get('id', ''))
            if not model_id:
                continue
            pricing = model.get('pricing') or {}
            try:
                prompt_price = float(pricing.get('prompt', 1))
                completion_price = float(pricing.get('completion', 1))
            except (TypeError, ValueError):
                continue
            is_free = (prompt_price == 0 and completion_price == 0) or model_id.endswith(':free')
            if not is_free:
                continue
            lowered = model_id.lower()
            if any(part in lowered for part in EXCLUDED_ID_PARTS):
                continue
            architecture = model.get('architecture') or {}
            outputs = architecture.get('output_modalities') or ['text']
            if 'text' not in outputs:
                continue
            context = int(model.get('context_length') or 0)
            if context < 16000:
                continue
            score = 0.0
            if model_id.endswith(':free'):
                score += 5
            for index, family in enumerate(PREFERRED_FAMILIES):
                if family in lowered:
                    score += 10 - index * 0.5
                    break
            if 32000 <= context <= 400000:
                score += 4
            elif context > 400000:
                score += 2
            if 'instruct' in lowered or 'it' in lowered:
                score += 1
            ranked.append((score, model_id))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [model_id for _, model_id in ranked]

    async def resolve_model(self, refresh: bool = False) -> str:
        if self.configured_model.lower() not in ('auto', 'free', ''):
            return self.configured_model
        if self._resolved_model and not refresh and time.monotonic() - self._resolved_at < 3600:
            return self._resolved_model
        try:
            models = await self.list_models()
            candidates = self._rank_free_models(models)
            if candidates:
                self._resolved_model = candidates[0]
                self._resolved_at = time.monotonic()
                logger.info('Selected OpenRouter free model: %s', self._resolved_model)
                return self._resolved_model
        except Exception as exc:
            logger.warning('Could not query OpenRouter model catalogue: %s', exc)
        self._resolved_model = 'openrouter/free'
        self._resolved_at = time.monotonic()
        return self._resolved_model

    def _fallback_models(self, primary: str) -> list[str]:
        models: list[str] = []
        for model in [primary, *settings.openrouter_fallback_list]:
            if model and model not in models:
                models.append(model)
        return models

    async def _post_completion(self, model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
        payload = {
            'model': model,
            'messages': messages,
            'temperature': settings.openrouter_temperature,
            'max_tokens': settings.openrouter_max_tokens,
        }
        timeout = httpx.Timeout(settings.openrouter_timeout_seconds, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f'{self.base_url}/chat/completions',
                headers=self.headers(),
                json=payload,
            )
        if response.status_code in (401, 403):
            raise OpenRouterAuthError('OpenRouter rejected the API key. Check OPENROUTER_API_KEY.')
        if response.status_code == 429:
            raise OpenRouterRateLimitError('OpenRouter rate limit reached.')
        if response.status_code >= 500:
            raise OpenRouterError(f'OpenRouter upstream error ({response.status_code}).')
        if response.status_code >= 400:
            detail = response.text[:300]
            raise OpenRouterError(f'OpenRouter request failed ({response.status_code}): {detail}')
        return response.json()

    async def chat(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        if not self.api_key:
            raise OpenRouterAuthError('OPENROUTER_API_KEY is not configured.')
        primary = await self.resolve_model()
        models = self._fallback_models(primary)
        last_error: Exception | None = None
        for model in models:
            for attempt in range(settings.openrouter_retries + 1):
                try:
                    data = await self._post_completion(model, messages)
                    choices = data.get('choices') or []
                    message = (choices[0] or {}).get('message') or {} if choices else {}
                    content = (message.get('content') or '').strip()
                    if not content:
                        content = (message.get('reasoning') or '').strip()
                    if not content:
                        raise OpenRouterError('OpenRouter returned an empty response.')
                    return {
                        'model': data.get('model') or model,
                        'content': content,
                        'usage': data.get('usage') or {},
                        'raw': data,
                    }
                except OpenRouterAuthError:
                    raise
                except OpenRouterRateLimitError as exc:
                    last_error = exc
                    if attempt < settings.openrouter_retries:
                        await asyncio.sleep(2.0 * (attempt + 1))
                        continue
                except (OpenRouterError, httpx.HTTPError) as exc:
                    last_error = exc
                    if attempt < settings.openrouter_retries:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
            logger.warning('OpenRouter model failed, trying next fallback: %s', model)
        raise OpenRouterError(str(last_error) if last_error else 'OpenRouter request failed.')

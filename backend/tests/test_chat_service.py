import pytest

from app.models.schemas import ChatRequest, ChatMessage
from app.services import chat as chat_service


class DummyRetriever:
    def __init__(self, chunks):
        self.chunks = chunks

    def retrieve(self, query, top_k=None, source_filter=None):
        return self.chunks

    def keyword_search(self, query, top_k=5, source_filter=None):
        return self.chunks


@pytest.mark.asyncio
async def test_generate_chat_response_no_results(monkeypatch):
    monkeypatch.setattr(chat_service, 'get_retriever', lambda: DummyRetriever([]))
    resp = await chat_service.generate_chat_response(ChatRequest(question='Unknown project details?'))
    assert 'could not find verified information' in resp.answer.lower()
    assert resp.sources == []
    assert resp.retrieved_count == 0


@pytest.mark.asyncio
async def test_generate_chat_response_with_sources_and_mocked_openrouter(monkeypatch):
    chunks = [
        {
            'chunk_id': 'c1', 'source': 'dar_global', 'url': 'https://darglobal.co.uk/marea',
            'title': 'Marea', 'content': 'Marea is a project in Spain by DarGlobal.', 'snippet': 'Marea in Spain',
            'metadata': {'site': 'DarGlobal', 'location': 'Spain'}
        },
        {
            'chunk_id': 'c2', 'source': 'wasalt', 'url': 'https://wasalt.sa/en/properties-for-sale-in-riyadh',
            'title': 'Properties for Sale in Riyadh', 'content': 'Wasalt lists properties for sale in Riyadh.',
            'snippet': 'Properties in Riyadh', 'metadata': {'site': 'Wasalt', 'location': 'Riyadh'}
        },
    ]
    monkeypatch.setattr(chat_service, 'get_retriever', lambda: DummyRetriever(chunks))
    monkeypatch.setattr(chat_service.settings, 'openrouter_api_key', 'test-key')

    class DummyClient:
        async def chat(self, messages):
            assert any(m['role'] == 'system' for m in messages)
            return {
                'model': 'test-free-model',
                'content': 'DarGlobal: Marea is in Spain. Wasalt: properties are listed in Riyadh. Sources: https://darglobal.co.uk/marea and https://wasalt.sa/en/properties-for-sale-in-riyadh',
                'usage': {},
            }

    monkeypatch.setattr(chat_service, 'OpenRouterClient', lambda: DummyClient())
    req = ChatRequest(question='Compare DarGlobal and Wasalt info', conversation_history=[ChatMessage(role='user', content='hi')])
    resp = await chat_service.generate_chat_response(req)
    assert resp.retrieved_count == 2
    assert len(resp.sources) == 2
    assert {s.source for s in resp.sources} == {'dar_global', 'wasalt'}
    assert resp.model == 'test-free-model'
    assert resp.degraded is False


@pytest.mark.asyncio
async def test_generate_chat_response_openrouter_error_falls_back(monkeypatch):
    chunks = [
        {
            'chunk_id': 'c1', 'source': 'dar_global', 'url': 'https://darglobal.co.uk/marea',
            'title': 'Marea', 'content': 'Marea is a project in Spain by DarGlobal.', 'snippet': 'Marea in Spain',
            'metadata': {'site': 'DarGlobal'}
        },
    ]
    monkeypatch.setattr(chat_service, 'get_retriever', lambda: DummyRetriever(chunks))
    monkeypatch.setattr(chat_service.settings, 'openrouter_api_key', 'test-key')

    class DummyClient:
        async def chat(self, messages):
            raise chat_service.OpenRouterError('rate limited')

    monkeypatch.setattr(chat_service, 'OpenRouterClient', lambda: DummyClient())
    resp = await chat_service.generate_chat_response(ChatRequest(question='Tell me about Marea'))
    assert resp.degraded is True
    assert resp.retrieved_count == 1
    assert len(resp.sources) == 1

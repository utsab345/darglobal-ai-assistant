from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    client = TestClient(app)
    r = client.get('/health')
    assert r.status_code == 200
    data = r.json()
    assert data['status'] == 'ok'
    assert 'knowledge_base_ready' in data


def test_stats_sources_projects_endpoints():
    client = TestClient(app)

    r = client.get('/api/stats')
    assert r.status_code == 200
    data = r.json()
    assert 'scrape' in data and 'knowledge_base' in data

    r = client.get('/api/sources')
    assert r.status_code == 200
    data = r.json()
    assert 'count' in data and 'sources' in data

    r = client.get('/api/projects')
    assert r.status_code == 200
    data = r.json()
    assert 'count' in data and 'projects' in data


def test_chat_validation_error():
    client = TestClient(app)
    r = client.post('/api/chat', json={'question': ''})
    assert r.status_code == 422


def test_chat_returns_grounded_response_structure():
    client = TestClient(app)
    r = client.post('/api/chat', json={'question': 'What properties does DarGlobal offer?', 'source_filter': 'dar_global'})
    assert r.status_code == 200
    data = r.json()
    assert 'answer' in data
    assert 'sources' in data
    assert 'retrieved_count' in data


def test_scrape_requires_token_when_configured(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, 'scrape_admin_token', 'secret-token')
    client = TestClient(app)
    r = client.post('/api/scrape', json={'sites': ['wasalt'], 'max_pages_per_site': 1})
    assert r.status_code in (401, 503)


def test_scrape_rejects_invalid_token(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, 'scrape_admin_token', 'secret-token')
    client = TestClient(app)
    r = client.post('/api/scrape', json={'sites': ['wasalt'], 'max_pages_per_site': 1}, headers={'X-Admin-Token': 'wrong'})
    assert r.status_code == 401

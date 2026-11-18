# DarGlobal and Wasalt Property Assistant

[![CI](https://github.com/utsab345/darglobal-ai-assistant/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/utsab345/darglobal-ai-assistant/actions/workflows/ci.yml)
[![Deployment](https://img.shields.io/badge/deployment-live-brightgreen)](https://darglobal-ai-assistant.onrender.com)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)](Dockerfile)
[![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](backend/requirements.txt)
[![React](https://img.shields.io/badge/react-18-20232A?logo=react&logoColor=61DAFB)](frontend/package.json)

A retrieval augmented chatbot for exploring publicly collected property information from DarGlobal and Wasalt. It combines a FastAPI backend, OpenRouter powered responses, a React frontend, and Docker deployment with source citations for grounded answers.

**Live demo:** https://darglobal-ai-assistant.onrender.com

## Highlights

- **Grounded Q&A:** Answers are generated from retrieved chunks in the collected dataset and include source links/citations.
- **Dual sources:** Search across DarGlobal, Wasalt, or all collected pages with a source filter.
- **OpenRouter integration:** Uses a free/available OpenRouter model (`OPENROUTER_MODEL=auto` by default) with graceful fallback to retrieved excerpts when unavailable.
- **Production ready packaging:** Multi-stage Docker image, Render blueprint, prebuilt knowledge base, and health checks.
- **Clean interface:** Responsive black and white UI focused on clarity, readable answers, and source inspection.

## Architecture

<img width="1536" height="1024" alt="archi" src="https://github.com/user-attachments/assets/e7d9cbec-c48c-424b-babb-a45a645fee25" />


## Dataset Snapshot

| Metric | Value |
|---|---|
| Raw documents loaded | 49 |
| Unique documents | 35 |
| Chunks | 242 |
| DarGlobal | 11 docs / 81 chunks |
| Wasalt | 24 docs / 161 chunks |
| Embeddings | `hash` (`hashed-tf-384`, dim 384) |
| Vector backend | FAISS |

Stats files: `backend/data/processed/kb_stats.json`, `backend/data/raw/last_scrape_summary.json`

> Note: DarGlobal pages can be protected by anti-bot controls for anonymous requests. The scraper respects `robots.txt` and site protections and does not bypass them, so DarGlobal coverage is limited to publicly accessible content collected.

## Tech Stack

- **Backend:** Python 3.12, FastAPI, Uvicorn, Pydantic, Requests, BeautifulSoup, NumPy, FAISS
- **RAG:** Chunking, hash embeddings, vector retrieval, source filtering, citation aware responses
- **LLM:** OpenRouter API (free model selection/fallback)
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS
- **Testing:** Pytest, pytest-asyncio, frontend production build checks
- **Deployment:** Docker, Render Blueprint, Nginx/Compose configs

## Repository Structure

```text
.
├── .github/workflows/ci.yml      # CI: backend tests + frontend build
├── backend/
│   ├── app/                      # API, services, RAG, scraping
│   ├── data/                     # Raw, processed, and vector store artifacts
│   ├── scripts/                  # Scrape, update, and stats utilities
│   └── tests/                    # Backend test suite
├── frontend/                     # React + TypeScript UI
├── docs/                         # Deployment notes
├── Dockerfile                    # Multi-stage production image
├── docker-compose.yml            # Local multi-container setup
└── render.yaml                   # Render deployment blueprint
```

## Quick Start (Local)

### 1. Backend

```bash
cp .env.example .env
python3 -m pip install -r backend/requirements.txt
PYTHONPATH=backend uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

### 2. Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- Health: `http://localhost:8000/health`
- API docs: `http://localhost:8000/docs`

## Docker

```bash
cp .env.example .env
docker compose up --build
```

- App (nginx): `http://localhost:8080`
- Backend: `http://localhost:8000`
- Health: `http://localhost:8000/health`

Single container image (serves API + built frontend):

```bash
docker build -t darglobal-ai-assistant .
docker run --rm -p 7860:7860 --env-file .env darglobal-ai-assistant
```

## Environment Variables

See `.env.example` and `frontend/.env.example`.

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | Enables live LLM answers via OpenRouter (optional for retrieved excerpt fallback) |
| `OPENROUTER_MODEL` | Model selection (`auto` recommended) |
| `OPENROUTER_BASE_URL` | OpenRouter API base URL |
| `EMBEDDING_PROVIDER` | Embedding provider (`hash` for lightweight deployment) |
| `AUTO_BUILD_KB` | Build knowledge base on startup if missing |
| `PORT` | Backend port (platform assigned in hosted environments) |
| `CORS_ORIGINS` | Allowed frontend origins |
| `SCRAPE_ADMIN_TOKEN` | Protects `POST /api/scrape` |
| `VITE_API_BASE_URL` | Frontend API base URL for split deployments |

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service and knowledge base status |
| `GET` | `/api/stats` | Dataset and scrape statistics |
| `GET` | `/api/sources` | Available sources |
| `GET` | `/api/projects` | Project/listing metadata from collected data |
| `POST` | `/api/chat` | Ask a question with source filter and history |
| `POST` | `/api/scrape` | Trigger scraping (requires `X-Admin-Token`) |

## Data Collection and Knowledge Base

```bash
PYTHONPATH=backend python3 backend/scripts/scrape.py --sites dar_global wasalt --max-pages 25
PYTHONPATH=backend python3 backend/scripts/update_data.py --sites dar_global wasalt --max-pages 25
PYTHONPATH=backend python3 backend/scripts/scrape_stats.py
```

The deployed image includes a prebuilt hash embedding knowledge base for fast startup. To update deployed data, rebuild the knowledge base locally and commit/push the updated artifacts.

## Testing and CI

Backend tests:

```bash
PYTHONPATH=backend PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest backend/tests -p pytest_asyncio.plugin -q
```

Frontend build:

```bash
cd frontend && npm ci && npm run build
```

CI runs automatically on push/PR via [GitHub Actions](.github/workflows/ci.yml) (backend tests + frontend build).

## Deployment

- **Render:** Deploy from this repository using `render.yaml` (Docker runtime, health check `/health`, prebuilt KB). Set `OPENROUTER_API_KEY` as a secret in the Render environment.
- **Docker hosts:** Use the root `Dockerfile` (exposes `7860` by default, compatible with Hugging Face Docker Spaces) or `docker-compose.yml` for multi-service setup.
- **Verification:** Check `GET /health` returns `knowledge_base_ready: true`, then test `POST /api/chat` and UI responses with citations.

## Limitations

- DarGlobal live scraping is limited by anti-bot protection; collected coverage may be incomplete.
- Dataset is a bounded snapshot of publicly accessible pages at collection time.
- Free OpenRouter models can change availability, rate limits, or response behavior.
- Without `OPENROUTER_API_KEY`, answers fall back to retrieved excerpts with sources.
- Hosted free tiers may cold start after inactivity; runtime filesystem updates are not persistent without rebuilding/redeploying.

## License

MIT. See [LICENSE](LICENSE).

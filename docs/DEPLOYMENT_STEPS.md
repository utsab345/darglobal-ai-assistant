# Deployment Steps (Hugging Face Spaces Docker / Generic Docker Host)

## Prerequisites
- Public Git repository (without `.env` or secrets)
- OpenRouter API key (`OPENROUTER_API_KEY`)
- Hosting account with Docker support (e.g. Hugging Face Spaces, Render)

## 1. Prepare repository
1. Ensure `.env` is not committed and `.env.example` is up to date.
2. Confirm tests pass locally:
   - `PYTHONPATH=backend:./.pydeps PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest backend/tests -p pytest_asyncio.plugin -q`
3. Confirm frontend builds:
   - `cd frontend && npm run build`

## 2. Configure environment variables on host
Set at minimum:
- `OPENROUTER_API_KEY=<your key>`
- `OPENROUTER_MODEL=auto` (or a currently available free model ID)
- `SCRAPE_ADMIN_TOKEN=<random strong token>`
- `CORS_ORIGINS=<your public frontend URL>`
- `APP_ENV=production`
- `AUTO_BUILD_KB=true`

If frontend and backend are deployed separately, also set:
- `VITE_API_BASE_URL=<public backend URL>` at frontend build time

## 3. Deploy (Docker Compose compatible host)
1. Upload/clone repo to host
2. Run `docker compose up --build -d`
3. Verify containers healthy
4. Check backend: `GET /health`
5. Check frontend loads and can send chat requests

## 4. Hugging Face Spaces (Docker) notes
- Use root Dockerfile strategy or Space build settings appropriate for the chosen layout (single-container combined or separate services).
- Persist `backend/data` if the platform supports persistent storage; otherwise bundle the dataset snapshot in the image.
- Expose the web port expected by the platform and set `PORT`/proxy config accordingly.

## 5. Post-deploy verification
- `GET /health` returns `200` and `knowledge_base_ready=true`
- `/api/stats` shows DarGlobal/Wasalt document counts
- `/api/chat` returns grounded answers with `sources` and `source_urls`
- UI source links open correctly
- Mobile layout is usable

## 6. Known blockers in this environment
- No hosting account credentials/token available for publishing a public URL
- DarGlobal live crawling is blocked by anti-bot challenge for anonymous requests; use bounded/approved collection strategy

# Sitemap Wrangler

Sitemap Wrangler is a small full-stack app that crawls a website and generates a `sitemap.xml` file.

## Stack

- Backend: Python 3.12+, FastAPI, httpx, asyncio, BeautifulSoup4, lxml, Pydantic
- Frontend: React + Vite + TypeScript
- Tooling: Docker, docker-compose, pytest, eslint, prettier

## Project Structure

```text
repo/
  backend/
    app/
      main.py
      api.py
      crawler.py
      robots.py
      sitemap.py
      models.py
      store.py
    tests/
    pyproject.toml
    Dockerfile
  frontend/
    src/
    vite.config.ts
    package.json
    Dockerfile
  docker-compose.yml
  README.md
```

## Local Development

### 1) Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

Backend runs at `http://localhost:8000`.

### 2) Frontend

```bash
cd frontend
npm install
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

Frontend runs at `http://localhost:5173`.

## Docker

Build and start both services:

```bash
docker-compose up --build
```

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`

## API

### Start crawl

```bash
curl -X POST "http://localhost:8000/api/crawl/start" \
  -H "Content-Type: application/json" \
  -d '{
    "site": "zollsoft.de",
    "max_pages": 500,
    "respect_robots": true,
    "include_query_params": false
  }'
```

### Check status

```bash
curl "http://localhost:8000/api/crawl/status/<job_id>"
```

### Download sitemap

```bash
curl -L "http://localhost:8000/api/crawl/download/<job_id>" -o sitemap.xml
```

## Testing

Backend tests:

```bash
cd backend
pytest
```

Frontend lint/format:

```bash
cd frontend
npm run lint
npm run format
```

## Notes

- Input normalization accepts `example.com`, `https://example.com`, and `http://example.com`.
- Crawler follows redirects and stores final normalized URLs.
- Private/local targets are rejected (localhost, 127/8, 10/8, 172.16/12, 192.168/16).
- Priority is deterministic and depth-based (`/` = `1.0`, then decrement by `0.1` per path segment, min `0.1`).

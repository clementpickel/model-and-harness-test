# YouTube Transcript Viewer

Browse YouTube video transcripts from the [@bycloudAI](https://www.youtube.com/@bycloudAI), [Fireship](https://www.youtube.com/@Fireship) and [T3](https://www.youtube.com/@t3dotgg) channels. No API key required — uses yt-dlp for open-source scraping.

## Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  React Frontend  │────▶│  FastAPI Backend │────▶│   YouTube/yt-dlp │
│  (Vite + TS)     │◀────│  + SQLite Cache   │◀────│   Scraper        │
│  Port 3000        │     │  Port 8000         │     └──────────────────┘
└──────────────────┘     └──────────────────┘
       │                         │
       │ nginx serves static    │ Persistent SQLite DB
       │ build + proxies /api    │ at /tmp/yt_transcripts.db
       ▼                         ▼
  Browser                    SQLite
```

### Components

| Component | Tech | Port | Description |
|-----------|------|------|-------------|
| Frontend | React 18 + Vite + TailwindCSS | 3000 | Light-themed SPA, serves static build |
| Backend | FastAPI + Python 3.12 + aiosqlite | 8000 | REST API, yt-dlp scraper, SQLite cache |
| nginx | Alpine-based | 3000 | Serves frontend build, proxies `/api/*` to backend |

### Channels

| Channel | URL |
|---------|-----|
| bycloudAI | https://www.youtube.com/@bycloudAI/videos |
| Fireship | https://www.youtube.com/@Fireship/videos |
| T3 | https://www.youtube.com/@t3dotgg/videos |

## API Endpoints

| Endpoint | Method | Description |
|---------|--------|-------------|
| `/api/videos` | GET | List all cached videos across all channels. Serves instantly from SQLite. |
| `/api/videos/{id}/transcript` | GET | Get transcript for a specific video. Fetches and caches on first request. |
| `/api/refresh` | POST | Trigger incremental background refresh of all channels. Returns immediately. |
| `/api/refresh/{channel_name}` | POST | Refresh a single channel only. |
| `/api/health` | GET | Health check with cached video count. |

## Local Development

### Prerequisites

- Python 3.12+
- Node.js 22+
- ffmpeg and curl (for yt-dlp subtitle fetching)

### Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start server (from backend/ dir, app/ is the python package)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API docs available at `http://localhost:8000/docs`

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start dev server (proxies /api to backend at :8000)
npm run dev
```

App available at `http://localhost:5173`

## Docker Deployment (Remote)

The project deploys as two separate containers on the remote server.

### Remote Server Requirements

- Docker installed on remote (`100.119.201.30`)
- Ports `3001` and `8001` available

### Deploy

From the project root (`yt-transcript-app/`):

```bash
# Default: deploy to 100.119.201.30 as current user
./deploy.sh

# Override server or user
SERVER=another.server.com USER=ubuntu ./deploy.sh
```

### What the deploy script does

1. Builds both Docker images locally (multi-stage, non-root)
2. Saves them as `.tar` files
3. SCP both images to remote home directory
4. SSH into remote, load both images into docker
5. Stop/remove existing containers, start new ones with volume mount for SQLite DB
6. Clean up tar files

### Access

- **Frontend**: http://100.119.201.30:3001
- **Backend API**: http://100.119.201.30:8001

### Remote Logs

```bash
# Backend logs
ssh clement@100.119.201.30 'docker logs -f yt-transcript-backend'

# Frontend logs
ssh clement@100.119.201.30 'docker logs -f yt-transcript-frontend'

# Restart containers
ssh clement@100.119.201.30 'docker restart yt-transcript-backend yt-transcript-frontend'
```

### SQLite Cache

The SQLite database lives at `/tmp/yt_transcripts.db` inside the backend container, mounted to `/home/clement/yt-transcript-app/backend_cache/yt_transcripts.db` on the host.

To reset all cached data:
```bash
ssh clement@100.119.201.30 'rm -f /home/clement/yt-transcript-app/backend_cache/yt_transcripts.db && docker restart yt-transcript-backend'
```

## Project Structure

```
yt-transcript-app/
├── deploy.sh                # Remote deployment script
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI entry point + lifespan
│   │   ├── config.py        # Settings (channels, cache TTL, CORS)
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   └── videos.py    # All /api/* routes
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── database.py  # SQLite cache (aiosqlite)
│   │   │   └── youtube.py   # yt-dlp wrapper + transcript parsing
│   │   └── schemas/
│   │       ├── __init__.py
│   │       └── video.py      # Pydantic models
│   ├── requirements.txt
│   └── Dockerfile            # Multi-stage, non-root user, healthcheck
└── frontend/
    ├── src/
    │   ├── api/client.ts
    │   ├── components/
    │   │   ├── VideoCard.tsx
    │   │   ├── SearchBar.tsx
    │   │   ├── TranscriptViewer.tsx
    │   │   ├── Modal.tsx
    │   │   └── LoadingSpinner.tsx
    │   ├── types/video.ts
    │   └── App.tsx
    ├── package.json
    ├── tailwind.config.js
    ├── vite.config.ts        # Proxies /api to localhost:8000
    ├── nginx.conf            # Production nginx config
    └── Dockerfile
```

## Configuration

All settings can be overridden via environment variables (prefix `YT_`):

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| `db_path` | `YT_DB_PATH` | `/tmp/yt_transcripts.db` | SQLite database path |
| `cache_ttl_seconds` | `YT_CACHE_TTL_SECONDS` | `300` | Video list cache TTL (unused, refresh is incremental) |
| `cors_origins` | `YT_CORS_ORIGINS` | localhost + clementpickel.fr | Allowed CORS origins (comma-separated) |
| `max_videos_per_channel` | `YT_MAX_VIDEOS_PER_CHANNEL` | `10` | Max videos to fetch per channel |
| Channels | — | bycloudAI, Fireship, T3 | Set via `ChannelConfig` in `config.py` |

## Refresh Behaviour

- **First load**: serves empty list `[]` and fires a background refresh. Page loads instantly.
- **Incremental refresh** (`POST /api/refresh`): compares upload dates, only inserts genuinely new videos. Existing videos and all transcripts are preserved.
- **Transcript caching**: transcripts are permanently cached once fetched. They are never invalidated.
- **`has_transcript` flag**: actually checked per-video via yt-dlp when videos are refreshed (concurrent), rather than assumed true.

## Tech Stack

- **Backend**: FastAPI, yt-dlp, Pydantic v2, aiosqlite, python-dotenv
- **Frontend**: React 18, Vite 6, TypeScript, TailwindCSS v3
- **Proxy/Web server**: nginx (production)
- **Container**: Docker, multi-stage python:3.12-slim, node:22-alpine

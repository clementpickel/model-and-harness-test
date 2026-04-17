# YouTube Transcript Viewer

Fetch and browse YouTube video transcripts from the [@bycloudAI](https://www.youtube.com/@bycloudAI) channel. No API key required — uses yt-dlp for open-source scraping.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  React Frontend │────▶│  FastAPI Backend │────▶│  YouTube/yt-dlp │
│  (Vite + TS)    │◀────│  + Disk Cache    │◀────│  Scraper        │
│  Port 3000      │     │  Port 8000       │     └─────────────────┘
└─────────────────┘     └─────────────────┘
        │                        │
        │ nginx serves static   │ JSON TTL cache
        │ build + proxies /api  │ at /tmp/video_cache
        ▼                        ▼
   Browser                  Disk
```

### Components

| Component | Tech | Port | Description |
|-----------|------|------|-------------|
| Frontend | React 18 + Vite + TailwindCSS | 3000 | Dark-themed SPA, serves static build |
| Backend | FastAPI + Python 3.12 | 8000 | REST API, yt-dlp scraper, cache |
| nginx | Alpine-based | 3000 | Serves frontend build, proxies `/api/*` to backend |

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/videos` | GET | List all cached videos from the channel |
| `/api/videos/{id}/transcript` | GET | Get transcript for a specific video |
| `/api/refresh` | POST | Trigger background refresh of video list |
| `/api/health` | GET | Health check |

## Local Development

### Prerequisites

- Python 3.12+
- Node.js 22+
- yt-dlp dependencies (ffprobe/ffmpeg recommended)

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
- Ports `3000` and `8000` available

### Deploy

From the project root (`yt-transcript-app/`):

```bash
# Default: deploy to 100.119.201.30 as current user
./deploy.sh

# Override server or user
SERVER=another.server.com USER=ubuntu ./deploy.sh
```

### What the deploy script does

1. Builds both Docker images locally
2. Saves them as `.tar` files
3. SCP both images to remote home directory
4. SSH into remote, load both images into docker
5. Stop/remove existing containers, start new ones
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

### Remote Cache

Video and transcript cache lives at `/home/clement/yt-transcript-app/backend_cache` on the remote server. The cache TTL is 5 minutes (configurable in `backend/app/config.py`).

To clear cache:
```bash
ssh clement@100.119.201.30 'sudo rm -rf /home/clement/yt-transcript-app/backend_cache/*'
```

## Project Structure

```
yt-transcript-app/
├── deploy.sh                # Remote deployment script
├── backend/
│   ├── app/
│   │   ├── main.py         # FastAPI entry point
│   │   ├── config.py       # Settings (channel URL, cache TTL)
│   │   ├── routers/videos.py
│   │   ├── services/
│   │   │   ├── youtube.py  # yt-dlp wrapper
│   │   │   └── cache.py    # Disk-based JSON cache
│   │   └── schemas/video.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── run.py
└── frontend/
    ├── src/
    │   ├── api/client.ts
    │   ├── components/
    │   │   ├── VideoCard.tsx
    │   │   ├── SearchBar.tsx
    │   │   ├── TranscriptViewer.tsx
    │   │   ├── Modal.tsx
    │   │   └── LoadingSpinner.tsx
    │   ├── hooks/useVideos.ts
    │   ├── types/video.ts
    │   └── App.tsx
    ├── package.json
    ├── tailwind.config.js
    ├── vite.config.ts       # Proxies /api to localhost:8000
    ├── nginx.conf           # Production nginx config
    └── Dockerfile
```

## Configuration

Edit `backend/app/config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `channel_url` | `https://www.youtube.com/@bycloudAI/videos` | YouTube channel to scrape |
| `max_videos` | `50` | Max videos to fetch |
| `cache_ttl_seconds` | `300` | Cache TTL (5 min) |
| `cache_dir` | `/tmp/video_cache` | Where cached data is stored |

## Tech Stack

- **Backend**: FastAPI, yt-dlp, Pydantic v2, python-dotenv
- **Frontend**: React 18, Vite 6, TypeScript, TailwindCSS v3
- **Proxy/Web server**: nginx (production)
- **Container**: Docker, python:3.12-slim, node:22-alpine

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import videos
from app.services.database import get_database
from app.config import settings

# Configure structured logging for the application
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize SQLite DB
    await get_database()
    logger.info("Database initialized at %s", settings.db_path)
    yield
    # Shutdown: close connection
    from app.services.database import _cache
    if _cache:
        await _cache.close()
        logger.info("Database connection closed")


app = FastAPI(
    title="YouTube Transcript Viewer",
    description="Fetch and display YouTube video transcripts",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware — origins configured via YT_CORS_ORIGINS env var
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(videos.router)


@app.get("/")
async def root():
    return {
        "message": "YouTube Transcript Viewer API",
        "docs": "/docs",
        "health": "/api/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

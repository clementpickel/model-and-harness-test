from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import videos
from contextlib import asynccontextmanager
from app.services.database import get_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize SQLite DB
    await get_database()
    yield
    # Shutdown: close connection
    from app.services.database import _cache
    if _cache:
        await _cache.close()


app = FastAPI(
    title="YouTube Transcript Viewer",
    description="Fetch and display YouTube video transcripts",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173", "https://transcript.clementpickel.fr"],
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
        "health": "/api/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
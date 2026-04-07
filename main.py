from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from db.base import Base
from db.session import engine
from routers import wardrobe, recommend, tryon


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import models.db_models  # noqa: F401 — register ORM models on Base.metadata

    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Stylo Berlin MVP",
    description="MVP backend for wardrobe, recommendations, and virtual try-on.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(wardrobe.router)
app.include_router(recommend.router)
app.include_router(tryon.router)

@app.get("/health")
async def health():
    return {"status": "ok"}

# Static UI last so /api/* and /docs stay reachable
app.mount("/", StaticFiles(directory="static", html=True), name="static")

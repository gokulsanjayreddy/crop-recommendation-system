from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.routers import recommend, history, meta
from backend.routers.history import seed_from_csv
from backend.config import settings

FRONTEND_DIR = str(settings.FRONTEND_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # load trained models once at startup (not per-request)
    from backend.inference import get_ranker
    get_ranker()
    seed_from_csv()
    yield


app = FastAPI(title="AI Crop Recommendation System", version="1.0.0",
              lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

app.include_router(recommend.router)
app.include_router(history.router)
app.include_router(meta.router)


@app.get("/")
def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

# static assets (app.js, vendor libs) - mounted last so API routes win
app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="frontend")

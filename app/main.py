from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.routes import router
from app.core.config import settings
from app.db.session import engine
from app.models.entities import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name}

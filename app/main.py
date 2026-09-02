from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.dashboard import router as dashboard_router
from app.api.routes import router
from app.core.config import settings
from app.core.middleware import SecurityMiddleware
from app.db.session import engine
from app.models.entities import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.env != "development":
        if settings.app_secret_key == "change-me-in-production":
            raise RuntimeError("APP_SECRET_KEY must be configured in production")
        if settings.service_api_token == "change-me-service-token":
            raise RuntimeError("SERVICE_API_TOKEN must be configured in production")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.3.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.env == "development" else None,
    redoc_url=None,
)
app.add_middleware(SecurityMiddleware)
app.include_router(router)
app.include_router(dashboard_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name}

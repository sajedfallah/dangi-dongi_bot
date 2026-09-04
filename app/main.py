from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dashboard import router as dashboard_router
from app.api.group_management import router as group_management_router
from app.api.product import router as product_router
from app.api.reminders_v2 import router as reminders_v2_router
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
    version="0.5.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.env == "development" else None,
    redoc_url=None,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Telegram-Init-Data"],
        expose_headers=["Retry-After"],
        max_age=600,
    )

app.add_middleware(SecurityMiddleware)
app.include_router(router)
app.include_router(dashboard_router)
app.include_router(product_router)
app.include_router(reminders_v2_router)
app.include_router(group_management_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name, "version": "0.5.0"}

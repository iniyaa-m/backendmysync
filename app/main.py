from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.config.settings import settings
from app.database.mongodb import connect_mongodb, close_mongodb
from app.database.redis_client import close_redis
from app.middleware.middleware import RequestLoggingMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware
from app.routes.auth_routes import router as auth_router
from app.routes.student_routes import router as student_router
from app.routes.teacher_routes import router as teacher_router
from app.routes.api_routes import (
    emotion_router, voice_router, chat_router, learning_router,
    analytics_router, notif_router, report_router, pdf_router, settings_router,
)
from app.websocket.ws_manager import router as ws_router
from app.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    await connect_mongodb()

    try:
        from app.database.mongodb import get_mongodb
        from app.services.gamification_service import seed_badges
        await seed_badges(get_mongodb())
        logger.info("Badges seeded")
    except Exception as e:
        logger.warning(f"Badge seeding failed (non-critical): {e}")

    logger.info("MongoDB initialized")
    yield

    logger.info("Shutting down...")
    await close_mongodb()
    await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="MindSync AI Classroom — Backend API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"

app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(student_router, prefix=API_PREFIX)
app.include_router(teacher_router, prefix=API_PREFIX)
app.include_router(emotion_router, prefix=API_PREFIX)
app.include_router(voice_router, prefix=API_PREFIX)
app.include_router(chat_router, prefix=API_PREFIX)
app.include_router(learning_router, prefix=API_PREFIX)
app.include_router(analytics_router, prefix=API_PREFIX)
app.include_router(notif_router, prefix=API_PREFIX)
app.include_router(report_router, prefix=API_PREFIX)
app.include_router(pdf_router, prefix=API_PREFIX)
app.include_router(settings_router, prefix=API_PREFIX)
app.include_router(ws_router)


@app.get("/", tags=["Health"])
async def root():
    return {"app": settings.APP_NAME, "version": settings.APP_VERSION, "status": "running", "docs": "/docs"}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy", "service": settings.APP_NAME}


@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": "Resource not found"})


@app.exception_handler(500)
async def server_error_handler(request, exc):
    logger.error(f"Server error: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

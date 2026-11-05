import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException

from app.api.auth import router as auth_router
from app.api.errors import AppError
from app.api.routes import router
from app.social.routes import router as social_router
from app.story.routes import router as story_router
from app.research.routes import router as research_router
from app.db import SessionLocal

app = FastAPI(title="Clipper API", version="0.1.0", docs_url="/api/v1/docs", openapi_url="/api/v1/openapi.json", redoc_url=None)
log = logging.getLogger("clipper.api")


class SocialAccessLogFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            args=list(record.args)
            if isinstance(args[2],str) and args[2].startswith('/api/v1/social/'):
                args[2]=args[2].split('?',1)[0]; record.args=tuple(args)
        return True


logging.getLogger('uvicorn.access').addFilter(SocialAccessLogFilter())


@app.middleware("http")
async def correlation(request: Request, call_next):
    request.state.correlation_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = request.state.correlation_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "private, no-store"
    return response


def error_response(request: Request, status: int, code: str, message: str):
    return JSONResponse(status_code=status, content={"code": code, "message": message, "correlation_id": getattr(request.state, "correlation_id", str(uuid4()))})


@app.exception_handler(AppError)
async def app_error(request: Request, exc: AppError):
    return error_response(request, exc.status, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Do not echo Pydantic input values: they may contain passwords or private text.
    return error_response(request, 422, "VALIDATION_ERROR", "Data tidak valid. Periksa waktu, nama, dan pengaturan yang dimasukkan.")


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return error_response(request, exc.status_code, "HTTP_ERROR", "Permintaan tidak dapat diproses.")


@app.exception_handler(IntegrityError)
async def conflict_error(request: Request, exc: IntegrityError):
    return error_response(request, 409, "CONFLICT", "Data berubah selama permintaan. Muat ulang dan coba lagi.")


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    # Log category and correlation only; SQL parameters and media/provider content are private.
    log.error("request_failed correlation_id=%s category=%s", getattr(request.state, "correlation_id", "unknown"), type(exc).__name__)
    return error_response(request, 500, "INTERNAL_ERROR", "Terjadi kesalahan server. Gunakan ID korelasi untuk pemeriksaan log.")


@app.get("/api/v1/health/live", tags=["health"])
def live():
    return {"status": "ok"}


@app.get("/api/v1/health/ready", tags=["health"])
def ready():
    from redis import Redis
    from app.config import get_settings
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        Redis.from_url(get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1).ping()
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}


app.include_router(auth_router, prefix="/api/v1")
app.include_router(router, prefix="/api/v1")
app.include_router(social_router, prefix="/api/v1")

app.include_router(story_router, prefix="/api/v1")
app.include_router(research_router, prefix="/api/v1")

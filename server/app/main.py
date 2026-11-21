"""FastAPI application factory for 小甘 (Lanzhou dialect conversation card)."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import routes_health, routes_media, routes_phrases, routes_records, routes_translate
from .api.errors import ApiError
from .config import Settings, get_settings
from .services.container import Container

logger = logging.getLogger("xiaogan.api")

_MEDIA_MAX_AGE_SECONDS = 86_400


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)


def _cleanup_media(media_dir: Path, max_age_seconds: int = _MEDIA_MAX_AGE_SECONDS) -> int:
    """Drop generated audio older than the signed-URL ceiling (spec 6.2)."""
    cutoff = time.time() - max_age_seconds
    removed = 0
    if not media_dir.exists():
        return 0
    for path in media_dir.iterdir():
        if path.is_file() and path.suffix in {".wav", ".mp3"} and path.stat().st_mtime < cutoff:
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "req_unknown")


def create_app(settings: Settings | None = None) -> FastAPI:
    _configure_logging()
    settings = settings or get_settings()
    container = Container(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        container.media.media_dir.mkdir(parents=True, exist_ok=True)
        removed = _cleanup_media(container.media.media_dir)
        if removed:
            logger.info("media_cleanup removed=%s", removed)
        logger.info(
            "startup version=%s env=%s mode=%s phrases=%s",
            settings.version,
            settings.env,
            settings.provider_mode,
            len(container.phrases.all()),
        )
        yield

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=(
            "兰州话 ↔ 普通话半双工对话后端。P0 只覆盖兰州话（试运行），"
            "不提供实时同传、医疗诊断或法律建议。"
        ),
        lifespan=lifespan,
    )
    app.state.container = container

    origins = ["*"] if settings.cors_origins.strip() == "*" else [
        item.strip() for item in settings.cors_origins.split(",") if item.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:16]}"
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - started) * 1000)
        response.headers["x-request-id"] = request_id
        # Privacy: only identifiers, timing and status are logged.
        logger.info(
            "http_request request_id=%s method=%s path=%s status=%s duration_ms=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        logger.warning(
            "api_error request_id=%s code=%s status=%s retryable=%s",
            _request_id(request),
            exc.code,
            exc.status_code,
            exc.retryable,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.payload(),
            headers={"x-request-id": _request_id(request)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        fields = []
        for error in exc.errors():
            location = ".".join(
                str(part) for part in error.get("loc", ()) if part not in {"body", "query", "form", "path"}
            )
            fields.append({"field": location or "body", "message": str(error.get("msg", ""))})
        logger.warning(
            "invalid_request request_id=%s fields=%s",
            _request_id(request),
            [item["field"] for item in fields],
        )
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "请求参数不合法。",
                    "retryable": False,
                    "details": {"fields": fields},
                }
            },
            headers={"x-request-id": _request_id(request)},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "http_error",
                    "message": str(exc.detail),
                    "retryable": False,
                    "details": {},
                }
            },
            headers={"x-request-id": _request_id(request)},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        logger.error(
            "unhandled_error request_id=%s path=%s type=%s",
            _request_id(request),
            request.url.path,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "服务暂时出错了，请重试或改用常用句。",
                    "retryable": True,
                    "details": {},
                }
            },
            headers={"x-request-id": _request_id(request)},
        )

    prefix = settings.api_prefix
    app.include_router(routes_translate.router, prefix=prefix)
    app.include_router(routes_phrases.router, prefix=prefix)
    app.include_router(routes_health.router, prefix=prefix)
    app.include_router(routes_records.router, prefix=prefix)
    app.include_router(routes_media.router)

    if settings.phrase_asset_dir.exists():
        app.mount(
            "/assets/phrases",
            StaticFiles(directory=str(settings.phrase_asset_dir)),
            name="phrase-assets",
        )

    @app.get("/")
    async def index():
        return {
            "name": settings.app_name,
            "version": settings.version,
            "docs": "/docs",
            "demo": "/demo",
            "health": f"{prefix}/health",
            "dialect": "lanzhou（试运行）",
        }

    demo_page = Path(__file__).resolve().parent / "static" / "demo.html"

    @app.get("/demo", include_in_schema=False)
    async def browser_demo():
        """H5 trial page: record in the browser and call the same API."""
        if not demo_page.exists():  # pragma: no cover - packaging guard
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "demo_page_missing", "message": "网页试用页未打包。", "retryable": False, "details": {}}},
            )
        return FileResponse(demo_page, media_type="text/html; charset=utf-8")

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)

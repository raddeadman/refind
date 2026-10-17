from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError
from starlette.middleware.sessions import SessionMiddleware

from . import db
from .config import get_settings
from .errors import ServiceError
from .routers import auth, categories, health
from .services import rate_limit


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await db.connect(settings.app_uri, settings.mongo_db)
    # TODO(M4/§4.5): start APScheduler here for item_service.archive_stale() at 03:00.
    yield
    rate_limit.close()
    await db.disconnect()


def operation_id(route: APIRoute) -> str:
    # The route function's name becomes the OpenAPI operationId, so Orval
    # generates hooks like useListCategories. Keep function names unique.
    return route.name


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ReFind API",
        description="Smart Lost & Found platform with automatic matching and claim verification.",
        version="0.1.0",
        lifespan=lifespan,
        generate_unique_id_function=operation_id,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Only holds the OAuth state/nonce between /google/login and the callback.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.jwt_secret,
        session_cookie="refind_oauth",
        max_age=600,
        same_site="lax",
    )

    @app.exception_handler(ServiceError)
    async def service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(DuplicateKeyError)
    async def duplicate_key(_: Request, exc: DuplicateKeyError) -> JSONResponse:
        # Never a 500 for a unique-index violation (§5.4).
        return JSONResponse(status_code=409, content={"detail": "Duplicate value"})

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(categories.router)
    return app


app = create_app()

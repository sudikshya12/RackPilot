"""RackOps Lab API: an independent interview lab for data center operations workflows."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .routers import acceptance, incidents, infra, platform
from .services.common import DomainError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = asyncio.Event()
    task = None
    if get_settings().runner_enabled:
        from .runner import runner_loop
        task = asyncio.create_task(runner_loop(stop))
    platform.prune_stream_events()
    yield
    stop.set()
    if task:
        await task


app = FastAPI(
    title="RackOps Lab API",
    version="1.0.0",
    description="Independent interview lab. Every measurement carries a source label: SIMULATED, LOCAL_LAB or IMPORTED_SAMPLE.",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=[get_settings().frontend_origin], allow_methods=["*"], allow_headers=["*"])

if get_settings().serverless:
    @app.middleware("http")
    async def _serverless_tick(request: Request, call_next):
        # No background process exists on serverless hosts: advance due work before serving the request.
        if request.url.path.startswith("/api/") and request.url.path != "/api/events":
            from .runner import lazy_tick
            await asyncio.to_thread(lazy_tick)
        return await call_next(request)


@app.exception_handler(DomainError)
async def domain_error(_: Request, exc: DomainError):
    return JSONResponse({"error": {"code": exc.code, "message": exc.message, "detail": exc.detail}}, status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    errs = [{"loc": ".".join(str(x) for x in e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    msg = "; ".join(f"{e['loc']}: {e['msg']}" for e in errs[:4])
    return JSONResponse({"error": {"code": "validation_error", "message": msg, "detail": {"errors": errs}}}, status_code=422)


for r in (platform.router, incidents.router, acceptance.router, infra.router):
    app.include_router(r)

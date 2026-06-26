from fastapi import FastAPI
from contextlib import asynccontextmanager
from backend.db.pool import create_pool, close_pool
from backend.db.health import check_postgres, check_redis, check_mlflow
from backend.db.migrations import run_migrations
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

# Telemetry
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

# Setup tracing
trace.set_tracer_provider(TracerProvider())

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await create_pool()
    await run_migrations()
    yield
    # Shutdown
    await close_pool()

from backend.api.ingest import router as ingest_router

app = FastAPI(title="NeuroFlow API", lifespan=lifespan)
app.include_router(ingest_router)

# Instrument the app
FastAPIInstrumentor.instrument_app(app)

@app.get("/health")
async def health_check():
    pg_ok = await check_postgres()
    redis_ok = await check_redis()
    mlflow_ok = await check_mlflow()
    
    all_ok = pg_ok and redis_ok and mlflow_ok
    status = "ok" if all_ok else "error"
    
    return {
        "status": status,
        "checks": {
            "postgres": pg_ok,
            "redis": redis_ok,
            "mlflow": mlflow_ok
        }
    }

@app.get("/metrics")
async def metrics():
    # Prometheus text format
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

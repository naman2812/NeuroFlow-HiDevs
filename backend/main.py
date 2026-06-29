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

from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from backend.config import settings

# Setup tracing
resource = Resource.create({"service.name": "neuroflow-api"})
provider = TracerProvider(resource=resource)
jaeger_endpoint = "http://jaeger:4317" if settings.postgres_host == "postgres" else "http://localhost:4317"
try:
    exporter = OTLPSpanExporter(endpoint=jaeger_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
except Exception:
    pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await create_pool()
    await run_migrations()
    yield
    # Shutdown
    await close_pool()

from backend.api import ingest, query, pipelines, compare, finetune
from backend.api.runs import router as runs_router

app = FastAPI(title="NeuroFlow API", lifespan=lifespan)
app.include_router(ingest.router)
app.include_router(query.router)
app.include_router(runs_router)
app.include_router(pipelines.router)
app.include_router(compare.router)
app.include_router(finetune.router)

# Instrument the app
FastAPIInstrumentor.instrument_app(app)

@app.get("/health")
async def health_check():
    pg_res = await check_postgres()
    redis_res = await check_redis()
    mlflow_res = await check_mlflow()
    
    try:
        import redis.asyncio as aioredis
        from backend.config import settings
        r = aioredis.from_url(f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}", decode_responses=True)
        
        cb_status = {}
        for provider in ["openai", "anthropic"]:
            state = await r.get(f"circuit:{provider}:state") or "closed"
            cb = {"state": state}
            if state == "open":
                cb["opened_at"] = await r.get(f"circuit:{provider}:opened_at")
            else:
                fails = await r.get(f"circuit:{provider}:failure_count")
                cb["failure_count"] = int(fails) if fails else 0
            cb_status[provider] = cb
            
        queue_depth = await r.llen("queue:ingest")
        # Optional: check arq queue depth as well if queue:ingest is empty
        if queue_depth == 0:
            queue_depth = await r.llen("arq:queue")
            
        workers = await r.scard("arq:workers")
        worker_count = workers if workers else 2 # default if none
        await r.aclose()
    except Exception:
        cb_status = {}
        queue_depth = 0
        worker_count = 0

    is_critical = pg_res["status"] == "error" or redis_res["status"] == "error"
    is_degraded = any(c["state"] == "open" for c in cb_status.values())
    all_checks_pass = pg_res["status"] == "ok" and redis_res["status"] == "ok" and mlflow_res["status"] == "ok"
    
    if is_critical:
        status = "critical"
    elif is_degraded or not all_checks_pass:
        status = "degraded"
    else:
        status = "ok"
    
    return {
        "status": status,
        "checks": {
            "postgres": pg_res,
            "redis": redis_res,
            "mlflow": mlflow_res,
            "circuit_breakers": cb_status,
            "queue_depth": queue_depth,
            "worker_count": worker_count
        }
    }

@app.get("/metrics")
async def metrics():
    # Prometheus text format
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

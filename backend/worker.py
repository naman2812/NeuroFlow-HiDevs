import asyncio
import asyncpg
from arq.connections import RedisSettings
from backend.config import settings
from backend.providers.client import NeuroFlowClient
from backend.pipelines.ingestion.pipeline import process_document_pipeline
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
import redis.asyncio as aioredis

async def startup(ctx):
    resource = Resource.create({"service.name": "neuroflow-worker"})
    provider = TracerProvider(resource=resource)
    
    # In local testing we might point to localhost, but jaeger is usually available via docker network
    jaeger_endpoint = "http://jaeger:4317" if "jaeger" in settings.redis_host else "http://localhost:4317"
    try:
        exporter = OTLPSpanExporter(endpoint=jaeger_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
    except Exception:
        pass
        
    ctx["db_pool"] = await asyncpg.create_pool(
        host=settings.postgres_host,
        user=settings.postgres_user,
        password=settings.postgres_password,
        database=settings.postgres_db,
        port=settings.postgres_port
    )
    
    redis_client = aioredis.from_url(
        f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}",
        decode_responses=True
    )
    ctx["llm_client"] = NeuroFlowClient(redis_client=redis_client)

async def shutdown(ctx):
    await ctx["db_pool"].close()

async def process_document(ctx, document_id: str, file_path: str, source_type: str):
    await process_document_pipeline(
        db_pool=ctx["db_pool"],
        client=ctx["llm_client"],
        document_id=document_id,
        file_path=file_path,
        source_type=source_type
    )

class WorkerSettings:
    functions = [process_document]
    redis_settings = RedisSettings(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password
    )
    on_startup = startup
    on_shutdown = shutdown

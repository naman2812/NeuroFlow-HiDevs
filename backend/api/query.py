import asyncio
import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.db.pool import get_pool
import redis.asyncio as aioredis
from backend.config import settings
from backend.providers.client import NeuroFlowClient

from pipelines.retrieval.pipeline import RetrievalPipeline
from pipelines.generation.generator import StreamingGenerator

router = APIRouter(prefix="/query", tags=["query"])

class QueryRequest(BaseModel):
    query: str
    pipeline_id: UUID
    stream: bool = False

async def get_redis():
    return aioredis.from_url(
        f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}",
        decode_responses=True
    )

@router.post("")
async def submit_query(req: QueryRequest, request: Request):
    pool = get_pool()
    
    # Create the run in DB
    async with pool.acquire() as conn:
        run_id = await conn.fetchval(
            """
            INSERT INTO pipeline_runs (pipeline_id, query, status)
            VALUES ($1, $2, 'pending')
            RETURNING id
            """,
            req.pipeline_id, req.query
        )
        
    if req.stream:
        return {"run_id": str(run_id)}
        
    # If not streaming, do it synchronously
    redis_client = await get_redis()
    client = NeuroFlowClient(redis_client)
    
    retrieval_pipeline = RetrievalPipeline(pool, client)
    generator = StreamingGenerator(client, pool, redis_client)
    
    # Fetch pipeline config
    pipeline_config = None
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT config FROM pipelines WHERE id = $1", req.pipeline_id)
        if row:
            pipeline_config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
            
    # Retrieval
    context_data = await retrieval_pipeline.get_context(req.query, config=pipeline_config)
    
    # Generation
    full_text = ""
    citations = []
    
    # We must iterate the async generator
    stream_gen = generator.generate_stream(str(run_id), str(req.pipeline_id), req.query, context_data.get("query_type", "factual"), context_data, config=pipeline_config)
    
    async for chunk, batch_citations in stream_gen:
        full_text += chunk
        if batch_citations:
            citations = batch_citations
            
    await redis_client.aclose()
            
    return {
        "run_id": str(run_id),
        "answer": full_text,
        "citations": citations,
        "context_sources": [
            {
                "document_name": s.metadata.get("filename", "unknown"),
                "chunk_id": str(s.chunk_id)
            }
            for s in context_data["raw_results"]
        ]
    }

@router.get("/{run_id}/stream")
async def stream_query(run_id: UUID, request: Request):
    pool = get_pool()
    
    # Verify run exists and is pending
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT query, pipeline_id FROM pipeline_runs WHERE id = $1",
            run_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
            
    query = row["query"]
    pipeline_id = row["pipeline_id"]
    
    redis_client = await get_redis()
    client = NeuroFlowClient(redis_client)
    
    retrieval_pipeline = RetrievalPipeline(pool, client)
    generator = StreamingGenerator(client, pool, redis_client)
    
    async def event_generator():
        try:
            # Keepalive task
            async def keepalive():
                try:
                    while True:
                        await asyncio.sleep(15)
                        yield {"event": "keepalive", "data": json.dumps({"type": "keepalive"})}
                except asyncio.CancelledError:
                    pass

            # Retrieval Start
            yield {"event": "message", "data": json.dumps({"type": "retrieval_start"})}
            
            # Since retrieval can take time, we should run it in a way that allows keepalive to interleave?
            # sse-starlette natively doesn't interleave easily unless we use asyncio.wait with timeout,
            # but we can just use a simple background task if needed, or rely on fast retrieval.
            # To strictly follow "keepalive event every 15s if generation takes long", we can use a queue.
            
            queue = asyncio.Queue()
            
            async def worker():
                try:
                    pipeline_config = None
                    async with pool.acquire() as conn:
                        row = await conn.fetchrow("SELECT config FROM pipelines WHERE id = $1", pipeline_id)
                        if row:
                            pipeline_config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]

                    context_data = await retrieval_pipeline.get_context(query, config=pipeline_config)
                    sources = [s.metadata.get("filename", f"doc_{s.document_id}") for s in context_data["raw_results"]]
                    
                    await queue.put({"type": "retrieval_complete", "chunk_count": len(sources), "sources": list(set(sources))})
                    
                    stream_gen = generator.generate_stream(str(run_id), str(pipeline_id), query, context_data.get("query_type", "factual"), context_data, config=pipeline_config)
                    async for chunk, batch_citations in stream_gen:
                        if chunk:
                            await queue.put({"type": "token", "delta": chunk})
                        if batch_citations:
                            await queue.put({"type": "done", "run_id": str(run_id), "citations": batch_citations})
                            break
                            
                    # If done without citations (empty output), send done anyway
                    if not batch_citations:
                        await queue.put({"type": "done", "run_id": str(run_id), "citations": []})
                except Exception as e:
                    await queue.put({"type": "error", "message": str(e)})
                    
            worker_task = asyncio.create_task(worker())
            
            while not worker_task.done() or not queue.empty():
                try:
                    # Wait for item with 15s timeout
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {"event": "message", "data": json.dumps(msg)}
                    
                    if msg.get("type") in ["done", "error"]:
                        break
                except asyncio.TimeoutError:
                    yield {"event": "message", "data": json.dumps({"type": "keepalive"})}
                    
        finally:
            await redis_client.aclose()
            
    return EventSourceResponse(event_generator())

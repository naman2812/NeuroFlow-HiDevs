import asyncio
import time
from uuid import UUID
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import redis.asyncio as aioredis
from typing import Dict, Any

import json
from backend.db.pool import get_pool
from backend.config import settings
from backend.providers.client import NeuroFlowClient
from pipelines.retrieval.pipeline import RetrievalPipeline
from pipelines.generation.generator import StreamingGenerator
from evaluation.judge import EvaluationJudge

router = APIRouter(prefix="/pipelines/compare", tags=["compare"])

class CompareRequest(BaseModel):
    query: str
    pipeline_a_id: UUID
    pipeline_b_id: UUID

async def get_redis():
    return aioredis.from_url(
        f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}",
        decode_responses=True
    )

async def run_pipeline(pool, redis_client, pipeline_id: UUID, query: str) -> Dict[str, Any]:
    # Fetch pipeline version and config to associate with run
    pipeline_config = None
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT version, config FROM pipelines WHERE id = $1", pipeline_id)
        if not row:
            raise ValueError(f"Pipeline {pipeline_id} not found")
        pipeline_version = row["version"]
        pipeline_config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
        
        run_id = await conn.fetchval(
            """
            INSERT INTO pipeline_runs (pipeline_id, pipeline_version, query, status)
            VALUES ($1, $2, $3, 'pending')
            RETURNING id
            """,
            pipeline_id, pipeline_version, query
        )
        
    start_time = time.time()
    
    client = NeuroFlowClient(redis_client)
    retrieval_pipeline = RetrievalPipeline(pool, client)
    generator = StreamingGenerator(client, pool, redis_client)
    
    try:
        # Retrieval
        retrieval_start = time.time()
        context_data = await retrieval_pipeline.get_context(query, config=pipeline_config)
        retrieval_latency_ms = int((time.time() - retrieval_start) * 1000)
        
        # Generation
        full_text = ""
        
        stream_gen = generator.generate_stream(str(run_id), str(pipeline_id), query, context_data.get("query_type", "factual"), context_data, config=pipeline_config)
        async for chunk, batch_citations in stream_gen:
            full_text += chunk
            
        total_latency_ms = int((time.time() - start_time) * 1000)
        
        # Update retrieval latency
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE pipeline_runs SET retrieval_latency_ms = $1 WHERE id = $2",
                retrieval_latency_ms, run_id
            )
            
        # Evaluation Job
        judge = EvaluationJudge(pool, redis_client)
        # Run it in background task (asyncio.create_task)
        # Note: in a real production system we use arq, but here create_task is acceptable
        asyncio.create_task(judge.evaluate_run(str(run_id)))
        
        return {
            "run_id": str(run_id),
            "generation": full_text,
            "retrieval_latency_ms": retrieval_latency_ms,
            "total_latency_ms": total_latency_ms,
            "chunks_used": len(context_data.get("raw_results", [])),
            "eval_score": None # Evaluates async
        }
    except Exception as e:
        async with pool.acquire() as conn:
            await conn.execute("UPDATE pipeline_runs SET status = 'failed' WHERE id = $1", run_id)
        raise e

@router.post("")
async def compare_pipelines(req: CompareRequest):
    pool = get_pool()
    redis_client = await get_redis()
    
    try:
        task_a = run_pipeline(pool, redis_client, req.pipeline_a_id, req.query)
        task_b = run_pipeline(pool, redis_client, req.pipeline_b_id, req.query)
        
        res_a, res_b = await asyncio.gather(task_a, task_b, return_exceptions=True)
        
        response = {"query": req.query}
        
        if isinstance(res_a, Exception):
            response["pipeline_a"] = {"error": str(res_a)}
        else:
            response["pipeline_a"] = res_a
            
        if isinstance(res_b, Exception):
            response["pipeline_b"] = {"error": str(res_b)}
        else:
            response["pipeline_b"] = res_b
            
        return response
    finally:
        await redis_client.aclose()

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime, timezone
from backend.db.pool import get_pool
from pipelines.finetuning.extractor import FineTuneExtractor
from pipelines.finetuning.tracker import FineTuneTracker
from pipelines.finetuning.job_manager import FineTuneManager
from backend.config import settings
from pydantic import BaseModel
import redis.asyncio as aioredis

from backend.security.auth import RequireScope

router = APIRouter(prefix="/finetune", tags=["finetune"])

class FineTuneRequest(BaseModel):
    base_model: str = "gpt-3.5-turbo-0613"
    format: str = "sft" # "sft" or "dpo"

async def get_redis():
    client = aioredis.from_url(
        f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}",
        decode_responses=True
    )
    try:
        yield client
    finally:
        await client.aclose()

@router.post("/jobs")
async def create_finetune_job(req: FineTuneRequest, db_pool=Depends(get_pool), redis_client=Depends(get_redis), user=Depends(RequireScope("admin"))):
    job_id = uuid4()
    
    if req.format not in ["sft", "dpo"]:
        raise HTTPException(status_code=400, detail="format must be 'sft' or 'dpo'")
    
    # Extract & Validate
    extractor = FineTuneExtractor(db_pool, redis_client)
    valid_pairs = await extractor.extract_for_job(job_id, format=req.format)
    
    if len(valid_pairs) < 10 and req.format == "sft": # Minimum pairs for OpenAI is usually 10
        raise HTTPException(status_code=400, detail=f"Not enough valid training pairs found (found {len(valid_pairs)}, need 10+)")
    elif len(valid_pairs) == 0 and req.format == "dpo":
        raise HTTPException(status_code=400, detail="No valid DPO pairs found")
        
    # Start MLflow run
    tracker = FineTuneTracker(tracking_uri="http://mlflow:5000" if settings.postgres_host == "postgres" else "http://localhost:5000")
    run_id = tracker.start_training_job(job_id, req.base_model, valid_pairs)
    
    # Submit job
    manager = FineTuneManager()
    try:
        provider_job_id = await manager.submit_finetune_job(f"training_data/{job_id}.jsonl", req.base_model)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit to OpenAI: {str(e)}")
        
    # Save job to DB
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO finetune_jobs (id, provider_job_id, base_model, status, training_pair_count, mlflow_run_id)
            VALUES ($1, $2, $3, 'pending', $4, $5)
            """,
            job_id, provider_job_id, req.base_model, len(valid_pairs), run_id
        )
        
    return {"job_id": job_id, "provider_job_id": provider_job_id, "status": "pending"}

@router.get("/jobs")
async def list_finetune_jobs(db_pool=Depends(get_pool), user=Depends(RequireScope("admin"))):
    async with db_pool.acquire() as conn:
        records = await conn.fetch("SELECT id, provider_job_id, base_model, status, created_at, completed_at FROM finetune_jobs ORDER BY created_at DESC")
    return [dict(r) for r in records]

@router.get("/jobs/{job_id}")
async def get_finetune_job(job_id: UUID, db_pool=Depends(get_pool), user=Depends(RequireScope("admin"))):
    async with db_pool.acquire() as conn:
        record = await conn.fetchrow("SELECT * FROM finetune_jobs WHERE id = $1", job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job_data = dict(record)
    job_data["mlflow_url"] = f"http://localhost:5000/#/experiments/0/runs/{record['mlflow_run_id']}"
    return job_data

@router.get("/training-data/preview")
async def preview_training_data(format: str = "sft", db_pool=Depends(get_pool), redis_client=Depends(get_redis), user=Depends(RequireScope("admin"))):
    if format not in ["sft", "dpo"]:
        raise HTTPException(status_code=400, detail="format must be 'sft' or 'dpo'")
        
    extractor = FineTuneExtractor(db_pool, redis_client)
    candidates = await extractor.get_dpo_candidates(limit=50) if format == "dpo" else await extractor.get_candidates(limit=50)
    
    valid_pairs = []
    for pair in candidates:
        if format == "sft":
            if await extractor.validate_pair(pair):
                valid_pairs.append(pair)
                if len(valid_pairs) == 5:
                    break
        else:
            # DPO doesn't have deep validation yet
            valid_pairs.append(pair)
            if len(valid_pairs) == 5:
                break
                
    return valid_pairs

import asyncio
import json
from uuid import UUID
from datetime import datetime, timezone
from openai import AsyncOpenAI
from backend.db.pool import get_pool
from pipelines.finetuning.tracker import FineTuneTracker
import redis.asyncio as aioredis
from backend.config import settings

class FineTuneManager:
    def __init__(self):
        self.api_key = settings.openai_api_key
        if self.api_key:
            self.client = AsyncOpenAI(api_key=self.api_key)
        else:
            self.client = None
        
    async def submit_finetune_job(self, jsonl_path: str, base_model: str) -> str:
        if not self.client:
            print("No OpenAI API key, mocking job submission")
            return f"ftjob-{UUID(int=1).hex}"
            
        file_resp = await self.client.files.create(
            file=open(jsonl_path, "rb"), 
            purpose="fine-tune"
        )
        job = await self.client.fine_tuning.jobs.create(
            training_file=file_resp.id, 
            model=base_model
        )
        return job.id

async def poll_finetune_jobs(ctx):
    """
    ARQ Cron job to poll active fine-tuning jobs.
    Runs every 60 seconds.
    """
    db_pool = ctx.get("db_pool")
    redis_client = ctx.get("redis_client")
    
    # Check if redis client exists, if not create one
    if not redis_client:
        redis_client = aioredis.from_url(
            f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}",
            decode_responses=True
        )
        
    # We create our own AsyncOpenAI client
    openai_client = AsyncOpenAI()
    tracker = FineTuneTracker(tracking_uri="http://mlflow:5000" if settings.postgres_host == "postgres" else "http://localhost:5000")
    
    async with db_pool.acquire() as conn:
        jobs = await conn.fetch(
            "SELECT id, provider_job_id, mlflow_run_id, base_model FROM finetune_jobs WHERE status = 'pending'"
        )
        
        for job_row in jobs:
            job_id = job_row["id"]
            provider_job_id = job_row["provider_job_id"]
            run_id = job_row["mlflow_run_id"]
            
            try:
                job_status = await openai_client.fine_tuning.jobs.retrieve(provider_job_id)
                
                if job_status.status == "succeeded":
                    # Get fine-tuned model name
                    fine_tuned_model = job_status.fine_tuned_model
                    
                    # Update status in DB
                    metrics = {
                        "training_token_count": getattr(job_status, "trained_tokens", 0)
                    }
                    
                    await conn.execute(
                        """
                        UPDATE finetune_jobs 
                        SET status = 'succeeded', completed_at = $1, metrics = $2, provider_job_id = $3
                        WHERE id = $4
                        """,
                        datetime.now(timezone.utc), json.dumps(metrics), fine_tuned_model, job_id
                    )
                    
                    # Register model in Redis
                    await redis_client.hset(
                        "router:models", 
                        fine_tuned_model, 
                        json.dumps({
                            "task_type": "rag", 
                            "base_model": job_row["base_model"],
                            "fine_tuned": True,
                            "finetune_job_id": str(job_id)
                        })
                    )
                    
                    # Log in MLflow
                    if run_id:
                        tracker.log_job_completion(run_id, job_id, fine_tuned_model, metrics)
                        
                elif job_status.status in ["failed", "cancelled"]:
                    await conn.execute(
                        "UPDATE finetune_jobs SET status = $1, completed_at = $2 WHERE id = $3",
                        job_status.status, datetime.now(timezone.utc), job_id
                    )
                    
            except Exception as e:
                print(f"Error polling finetune job {job_id}: {e}")

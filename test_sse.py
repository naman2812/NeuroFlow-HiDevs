import asyncio
import json
import logging
import uuid
import httpx

from backend.main import app
from backend.db.pool import get_pool, create_pool, close_pool
from fastapi.testclient import TestClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    await create_pool()
    pool = get_pool()
    
    pipeline_id = uuid.uuid4()
    pipeline_name = f"Test Pipeline {pipeline_id}"
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO pipelines (id, name, config) VALUES ($1, $2, $3)",
            pipeline_id, pipeline_name, "{}"
        )
    await close_pool()

    with TestClient(app) as client:
        logger.info("POST /query with stream=True")
        req_body = {
            "query": "Compare attention with memory?",
            "pipeline_id": str(pipeline_id),
            "stream": True
        }
        
        post_res = client.post("/query", json=req_body)
        assert post_res.status_code == 200, post_res.text
        run_id = post_res.json()["run_id"]
        logger.info(f"Got run_id: {run_id}")
        
        logger.info("Consuming GET /query/{run_id}/stream")
        with client.stream("GET", f"/query/{run_id}/stream") as response:
            for line in response.iter_lines():
                if line:
                    logger.info(f"SSE EVENT: {line}")

if __name__ == "__main__":
    asyncio.run(main())

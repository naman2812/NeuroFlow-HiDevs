import pytest
import asyncio
import httpx
import subprocess
import time
import logging

logger = logging.getLogger(__name__)

REDIS_CONTAINER = "infra-redis-1"
WORKER_CONTAINER = "infra-worker-1"
API_URL = "http://localhost:8000"

def get_container_id(name):
    try:
        result = subprocess.run(["docker", "ps", "-q", "-f", f"name={name}"], capture_output=True, text=True)
        return result.stdout.strip()
    except Exception as e:
        logger.error(f"Failed to get container ID for {name}: {e}")
        return None

def stop_container(name):
    logger.info(f"Killing container {name}...")
    subprocess.run(["docker", "kill", name], check=True)
    time.sleep(2)

def start_container(name):
    logger.info(f"Starting container {name}...")
    subprocess.run(["docker", "start", name], check=True)
    time.sleep(5)

@pytest.mark.asyncio
async def test_redis_chaos_degrades_gracefully():
    # 1. Verify system is healthy initially
    async with httpx.AsyncClient(base_url=API_URL) as client:
        res = await client.get("/health")
        if res.status_code != 200:
            pytest.skip("API is not running on localhost:8000")
            
        redis_id = get_container_id(REDIS_CONTAINER)
        if not redis_id:
            pytest.skip(f"{REDIS_CONTAINER} is not running")
        
        try:
            # 2. Kill Redis
            stop_container(REDIS_CONTAINER)
            
            # 3. Verify system degrades gracefully (does not crash)
            res = await client.get("/health")
            assert res.status_code == 200
            
            # Even without Redis, the core API should stay up
            logger.info(f"Health after Redis kill: {res.json()}")
            
        finally:
            # 4. Restore Redis
            start_container(REDIS_CONTAINER)
            
        # 5. Verify full recovery
        res = await client.get("/health")
        assert res.status_code == 200

@pytest.mark.asyncio
async def test_worker_chaos_requeues_jobs():
    worker_id = get_container_id(WORKER_CONTAINER)
    if not worker_id:
        pytest.skip(f"{WORKER_CONTAINER} is not running")
        
    async with httpx.AsyncClient(base_url=API_URL) as client:
        res = await client.post("/auth/token", json={"client_id": "admin", "client_secret": "test"})
        token = res.json().get("access_token") if res.status_code == 200 else None
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        
        try:
            # 1. Submit ingestion job
            with open("tests/fixtures/test_doc.pdf", "rb") as f:
                res = await client.post("/ingest", files={"file": ("test_doc.pdf", f, "application/pdf")}, headers=headers)
                assert res.status_code == 200
                doc_id = res.json()["document_id"]
            
            # 2. Immediately kill worker (simulating mid-processing failure or immediately after queue)
            stop_container(WORKER_CONTAINER)
            
            # 3. Verify status is still pending or processing
            res = await client.get(f"/ingest/{doc_id}", headers=headers)
            assert res.json()["status"] in ["pending", "processing"]
            
        finally:
            # 4. Restart worker
            start_container(WORKER_CONTAINER)
            
        # 5. Verify job eventually completes (ARQ re-queues or picks it up)
        start_time = time.time()
        completed = False
        while time.time() - start_time < 45:
            res = await client.get(f"/ingest/{doc_id}", headers=headers)
            if res.status_code == 200 and res.json()["status"] == "complete":
                completed = True
                break
            await asyncio.sleep(2)
            
        assert completed, f"Job {doc_id} did not recover and complete after worker restart!"

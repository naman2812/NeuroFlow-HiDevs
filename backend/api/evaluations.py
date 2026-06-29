import json
import asyncio
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
from backend.config import settings
import redis.asyncio as aioredis

router = APIRouter(prefix="/evaluations", tags=["evaluations"])

@router.get("/stream")
async def stream_evaluations(request: Request):
    """
    Subscribe to real-time evaluations using SSE.
    """
    async def event_generator():
        r = aioredis.from_url(
            f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}",
            decode_responses=True
        )
        pubsub = r.pubsub()
        await pubsub.subscribe("evaluations:new")
        
        try:
            while True:
                if await request.is_disconnected():
                    break
                    
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
                if message and message["type"] == "message":
                    yield {"event": "message", "data": message["data"]}
                elif message is None:
                    # Keepalive
                    yield {"event": "keepalive", "data": json.dumps({"type": "keepalive"})}
        finally:
            await pubsub.unsubscribe("evaluations:new")
            await pubsub.close()
            await r.aclose()
            
    return EventSourceResponse(event_generator())

from pydantic import BaseModel
import uuid
from datetime import datetime

class SimulateEval(BaseModel):
    pipeline_name: str = "Test Pipeline"
    query: str = "What is the capital of France?"

@router.post("/simulate")
async def simulate_eval(req: SimulateEval):
    # Simulate a run ID and random metrics
    import random
    
    eval_dict = {
        "id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "pipeline_name": req.pipeline_name,
        "query": req.query,
        "faithfulness": random.uniform(0.6, 1.0),
        "answer_relevance": random.uniform(0.5, 0.95),
        "context_precision": random.uniform(0.7, 1.0),
        "context_recall": random.uniform(0.4, 0.9),
        "overall_score": random.uniform(0.6, 0.95),
        "evaluated_at": datetime.utcnow().isoformat() + "Z",
        "retrieved_chunks": ["Paris is the capital of France."],
        "generated_answer": "The capital of France is Paris."
    }
    
    r = aioredis.from_url(
        f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}",
        decode_responses=True
    )
    
    await r.publish("evaluations:new", json.dumps(eval_dict))
    await r.aclose()
    
    return {"status": "simulated", "eval": eval_dict}

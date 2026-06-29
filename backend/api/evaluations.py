import json
import asyncio
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
from backend.config import settings
import redis.asyncio as aioredis
from opentelemetry import trace
from backend.monitoring.metrics import eval_faithfulness, eval_overall

tracer = trace.get_tracer(__name__)

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
    
    with tracer.start_as_current_span("evaluation.judge") as judge_span:
        judge_span.set_attribute("pipeline_id", req.pipeline_name)
        
        with tracer.start_as_current_span("evaluation.faithfulness") as f_span:
            faithfulness = random.uniform(0.6, 1.0)
            f_span.set_attribute("score", faithfulness)
            
        with tracer.start_as_current_span("evaluation.answer_relevance") as ar_span:
            answer_relevance = random.uniform(0.5, 0.95)
            ar_span.set_attribute("score", answer_relevance)
            
        with tracer.start_as_current_span("evaluation.context_precision") as cp_span:
            context_precision = random.uniform(0.7, 1.0)
            cp_span.set_attribute("score", context_precision)
            
        with tracer.start_as_current_span("evaluation.context_recall") as cr_span:
            context_recall = random.uniform(0.4, 0.9)
            cr_span.set_attribute("score", context_recall)
            
        overall_score = random.uniform(0.6, 0.95)
        judge_span.set_attribute("overall_score", overall_score)
        
        eval_dict = {
            "id": str(uuid.uuid4()),
            "run_id": str(uuid.uuid4()),
            "pipeline_name": req.pipeline_name,
            "query": req.query,
            "faithfulness": faithfulness,
            "answer_relevance": answer_relevance,
            "context_precision": context_precision,
            "context_recall": context_recall,
            "overall_score": overall_score,
            "evaluated_at": datetime.utcnow().isoformat() + "Z",
            "retrieved_chunks": ["Paris is the capital of France."],
            "generated_answer": "The capital of France is Paris."
        }
        
        # Update gauges
        eval_faithfulness.labels(pipeline_id=req.pipeline_name).set(faithfulness)
        eval_overall.labels(pipeline_id=req.pipeline_name).set(overall_score)
        
        r = aioredis.from_url(
            f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}",
            decode_responses=True
        )
        
        await r.publish("evaluations:new", json.dumps(eval_dict))
        await r.aclose()
        
        return {"status": "simulated", "eval": eval_dict}

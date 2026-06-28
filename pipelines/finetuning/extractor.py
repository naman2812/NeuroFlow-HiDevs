import json
import os
import re
import tiktoken
from uuid import UUID
from typing import List, Dict, Any
from backend.providers.client import NeuroFlowClient
from evaluation.metrics.faithfulness import evaluate_faithfulness

# Simple PII patterns
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
PHONE_REGEX = re.compile(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b')
CITATION_REGEX = re.compile(r'\[Source \d+\]')

class FineTuneExtractor:
    def __init__(self, db_pool, redis_client=None):
        self.db_pool = db_pool
        self.client = NeuroFlowClient(redis_client) if redis_client else None
        self.encoding = tiktoken.get_encoding("cl100k_base")

    async def get_candidates(self, limit: int = 1000) -> List[Dict[str, Any]]:
        # Query matching conditions
        query = """
            SELECT 
                tp.id, tp.run_id, tp.system_prompt, tp.user_message, tp.assistant_message, tp.quality_score,
                e.user_rating, e.faithfulness
            FROM training_pairs tp
            LEFT JOIN evaluations e ON e.run_id = tp.run_id
            WHERE tp.quality_score >= 0.82
              AND tp.included_in_job IS NULL
              AND (e.user_rating >= 4 OR e.user_rating IS NULL)
            LIMIT $1
        """
        async with self.db_pool.acquire() as conn:
            records = await conn.fetch(query, limit)
            
        return [dict(r) for r in records]

    async def validate_pair(self, pair: Dict[str, Any]) -> bool:
        # PII Check on query (user_message)
        user_msg = pair.get("user_message", "")
        if EMAIL_REGEX.search(user_msg) or PHONE_REGEX.search(user_msg):
            return False
            
        assistant_msg = pair.get("assistant_message", "")
        
        # Token length check
        tokens = len(self.encoding.encode(assistant_msg))
        if tokens < 50 or tokens > 2000:
            return False
            
        # Citation check
        if not CITATION_REGEX.search(assistant_msg):
            return False
            
        # Always Re-evaluate faithfulness
        if not self.client:
            return False
            
        # To evaluate faithfulness, we need context. We fetch context from chunks.
        run_id = pair.get("run_id")
        async with self.db_pool.acquire() as conn:
            run_row = await conn.fetchrow("SELECT retrieved_chunk_ids FROM pipeline_runs WHERE id = $1", run_id)
            if not run_row or not run_row["retrieved_chunk_ids"]:
                return False
            
            chunk_ids = run_row["retrieved_chunk_ids"]
            chunk_rows = await conn.fetch("SELECT content FROM chunks WHERE id = ANY($1)", chunk_ids)
            context = "\n".join([r["content"] for r in chunk_rows])
            
        try:
            faithfulness = await evaluate_faithfulness(
                query=user_msg, 
                generation=assistant_msg, 
                context=context, 
                client=self.client
            )
        except Exception:
            return False
            
        if faithfulness is None or faithfulness <= 0.8:
            return False
            
        return True

    def format_jsonl_message(self, pair: Dict[str, Any], context: str = "") -> str:
        messages = []
        if pair.get("system_prompt"):
            messages.append({"role": "system", "content": pair["system_prompt"]})
        
        user_msg = pair["user_message"]
        if context:
            user_msg = f"[Context]\n{context}\n[Question]\n{user_msg}"
            
        messages.append({"role": "user", "content": user_msg})
        messages.append({"role": "assistant", "content": pair["assistant_message"]})
        
        return json.dumps({"messages": messages})

    async def get_context_for_run(self, run_id: UUID) -> str:
        async with self.db_pool.acquire() as conn:
            run_row = await conn.fetchrow("SELECT retrieved_chunk_ids FROM pipeline_runs WHERE id = $1", run_id)
            if not run_row or not run_row["retrieved_chunk_ids"]:
                return ""
            
            chunk_ids = run_row["retrieved_chunk_ids"]
            if not chunk_ids:
                return ""
            chunk_rows = await conn.fetch("SELECT content FROM chunks WHERE id = ANY($1)", chunk_ids)
            return "\n".join([r["content"] for r in chunk_rows])

    async def extract_for_job(self, job_id: UUID) -> List[Dict[str, Any]]:
        candidates = await self.get_candidates()
        valid_pairs = []
        
        for pair in candidates:
            if await self.validate_pair(pair):
                # Fetch context for the valid pair to include in the JSONL
                context = await self.get_context_for_run(pair["run_id"])
                pair["context"] = context
                valid_pairs.append(pair)
                
        if not valid_pairs:
            return []
            
        # Write to JSONL
        os.makedirs("training_data", exist_ok=True)
        file_path = f"training_data/{job_id}.jsonl"
        with open(file_path, "w", encoding="utf-8") as f:
            for pair in valid_pairs:
                f.write(self.format_jsonl_message(pair, pair.get("context", "")) + "\n")
                
        # Update included_in_job in database
        pair_ids = [p["id"] for p in valid_pairs]
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE training_pairs SET included_in_job = $1 WHERE id = ANY($2)",
                job_id, pair_ids
            )
            
        return valid_pairs

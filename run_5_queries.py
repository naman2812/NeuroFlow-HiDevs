import asyncio
import httpx
import json
import logging
logger = logging.getLogger(__name__)



API_URL = "http://localhost:8000"

async def main():
    async with httpx.AsyncClient(timeout=120.0) as client:
        # Create pipeline A
        pipe_a_data = {
            "config": {
                "name": "Pipeline A - High Precision",
                "description": "Uses low top_k and low temperature",
                "ingestion": {"chunking_strategy": "hierarchical", "chunk_size_tokens": 512, "chunk_overlap_tokens": 64, "extractors_enabled": ["pdf"]},
                "retrieval": {"dense_k": 20, "sparse_k": 20, "reranker": "cross-encoder", "top_k_after_rerank": 3, "query_expansion": True, "metadata_filters_enabled": False},
                "generation": {"model_routing": {"task_type": "rag", "max_cost_per_call": 0.05}, "system_prompt_variant": "factual", "max_context_tokens": 4000, "temperature": 0.1},
                "evaluation": {"auto_evaluate": True, "training_threshold": 0.8}
            }
        }
        res_a = await client.post(f"{API_URL}/pipelines", json=pipe_a_data)
        pipe_a_id = res_a.json()["id"]
        
        # Create pipeline B
        pipe_b_data = {
            "config": {
                "name": "Pipeline B - High Recall",
                "description": "Uses high top_k and higher temperature",
                "ingestion": {"chunking_strategy": "hierarchical", "chunk_size_tokens": 512, "chunk_overlap_tokens": 64, "extractors_enabled": ["pdf"]},
                "retrieval": {"dense_k": 50, "sparse_k": 50, "reranker": "cross-encoder", "top_k_after_rerank": 10, "query_expansion": True, "metadata_filters_enabled": False},
                "generation": {"model_routing": {"task_type": "rag", "max_cost_per_call": 0.05}, "system_prompt_variant": "factual", "max_context_tokens": 6000, "temperature": 0.7},
                "evaluation": {"auto_evaluate": True, "training_threshold": 0.8}
            }
        }
        res_b = await client.post(f"{API_URL}/pipelines", json=pipe_b_data)
        pipe_b_id = res_b.json()["id"]
        
        logger.info(f"Created Pipeline A: {pipe_a_id}")
        logger.info(f"Created Pipeline B: {pipe_b_id}")
        
        queries = [
            "What is the capital of France?",
            "How does quantum computing work?",
            "Explain the theory of relativity.",
            "What is the difference between a virus and bacteria?",
            "What is the liability clause in the MSA?"
        ]
        
        for i, query in enumerate(queries):
            logger.info(f"\\n--- Query {i+1}: {query} ---")
            req = {
                "query": query,
                "pipeline_a_id": pipe_a_id,
                "pipeline_b_id": pipe_b_id
            }
            res_comp = await client.post(f"{API_URL}/pipelines/compare", json=req)
            data = res_comp.json()
            
            # Print evaluation scores
            score_a = data.get("pipeline_a", {}).get("eval_score")
            score_b = data.get("pipeline_b", {}).get("eval_score")
            
            logger.info(f"Pipeline A eval_score: {score_a}")
            logger.info(f"Pipeline B eval_score: {score_b}")
            
            if score_a is not None and score_b is not None:
                logger.info("[SUCCESS] Both pipelines returned evaluation scores!")
            else:
                logger.info("[FAILED] Missing evaluation score(s).")
                logger.info("Response:", json.dumps(data, indent=2))

if __name__ == "__main__":
    asyncio.run(main())

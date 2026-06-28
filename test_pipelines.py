import asyncio
import json
import httpx
from uuid import UUID, uuid4

API_URL = "http://localhost:8000"

async def test_pipelines():
    uid = str(uuid4())[:8]
    async with httpx.AsyncClient(timeout=60.0) as client:
        print("1. Creating Pipeline A")
        config_a = {
            "config": {
                "name": f"legal-research-v1-{uid}",
                "description": "Pipeline A",
                "ingestion": {
                    "chunking_strategy": "hierarchical",
                    "chunk_size_tokens": 400,
                    "chunk_overlap_tokens": 80,
                    "extractors_enabled": ["pdf"]
                },
                "retrieval": {
                    "dense_k": 30,
                    "sparse_k": 20,
                    "reranker": "cross-encoder",
                    "top_k_after_rerank": 8,
                    "query_expansion": True,
                    "metadata_filters_enabled": True
                },
                "generation": {
                    "model_routing": {"task_type": "rag_generation", "max_cost_per_call": 0.05},
                    "max_context_tokens": 6000,
                    "temperature": 0.2,
                    "system_prompt_variant": "precise"
                },
                "evaluation": {
                    "auto_evaluate": True,
                    "training_threshold": 0.82
                }
            }
        }
        resp_a = await client.post(f"{API_URL}/pipelines", json=config_a)
        if resp_a.status_code != 200:
            print(f"Error creating A: {resp_a.text}")
            return
        pipe_a_id = resp_a.json()["id"]
        print(f"Pipeline A created: {pipe_a_id}")
        
        print("2. Creating Pipeline B")
        config_b = config_a.copy()
        config_b["config"]["name"] = f"legal-research-v2-{uid}"
        config_b["config"]["generation"]["temperature"] = 0.7
        resp_b = await client.post(f"{API_URL}/pipelines", json=config_b)
        pipe_b_id = resp_b.json()["id"]
        print(f"Pipeline B created: {pipe_b_id}")
        
        print("3. Updating Pipeline A (Versioning test)")
        update_data = config_a.copy()
        update_data["config"]["description"] = "Pipeline A - Updated"
        resp_patch = await client.patch(f"{API_URL}/pipelines/{pipe_a_id}", json=update_data)
        print(f"Pipeline A version is now: {resp_patch.json()['version']}")
        
        print("4. Fetching Analytics for A")
        resp_analytics = await client.get(f"{API_URL}/pipelines/{pipe_a_id}/analytics")
        print(f"Analytics: {resp_analytics.json()}")
        
        print("5. Comparing A and B")
        compare_data = {
            "query": "What is the liability clause in the MSA?",
            "pipeline_a_id": pipe_a_id,
            "pipeline_b_id": pipe_b_id
        }
        resp_compare = await client.post(f"{API_URL}/pipelines/compare", json=compare_data)
        print("Compare Result:")
        print(json.dumps(resp_compare.json(), indent=2))
        
        print("6. Getting pipelines list")
        resp_list = await client.get(f"{API_URL}/pipelines")
        print(f"Pipelines found: {len(resp_list.json())}")

if __name__ == "__main__":
    asyncio.run(test_pipelines())

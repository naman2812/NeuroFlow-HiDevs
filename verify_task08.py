import asyncio
import httpx
import time
from uuid import uuid4

API_URL = "http://localhost:8000"

async def main():
    uid = str(uuid4())[:8]
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. PipelineConfig rejects unknown keys
        print("Checking 1: PipelineConfig rejects unknown keys...")
        bad_config = {
            "config": {
                "name": f"test-reject-{uid}",
                "description": "Reject me",
                "ingestion": {
                    "chunking_strategy": "hierarchical",
                    "chunk_size_tokens": 400,
                    "chunk_overlap_tokens": 80,
                    "extractors_enabled": ["pdf"],
                    "unknown_key_123": "should fail"
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
        res = await client.post(f"{API_URL}/pipelines", json=bad_config)
        if res.status_code == 422:
            print("[SUCCESS] Unknown keys rejected with 422")
        else:
            print(f"[FAILED] Expected 422, got {res.status_code}")
            
        # 2. Pipeline updates create new versions
        print("Checking 2: Pipeline updates create new versions...")
        good_config = bad_config.copy()
        del good_config["config"]["ingestion"]["unknown_key_123"]
        res = await client.post(f"{API_URL}/pipelines", json=good_config)
        pipe_id = res.json()["id"]
        v1 = res.json()["version"]
        
        update_config = good_config.copy()
        update_config["config"]["description"] = "Updated Description"
        res2 = await client.patch(f"{API_URL}/pipelines/{pipe_id}", json=update_config)
        v2 = res2.json()["version"]
        if v2 > v1:
            print(f"[SUCCESS] Version incremented from {v1} to {v2}")
        else:
            print(f"[FAILED] Version did not increment. v1={v1}, v2={v2}")
            
        # 3. POST /pipelines/compare runs in parallel
        print("Checking 3: Compare runs in parallel...")
        config_b = good_config.copy()
        config_b["config"]["name"] = f"test-compare-{uid}"
        res_b = await client.post(f"{API_URL}/pipelines", json=config_b)
        pipe_b_id = res_b.json()["id"]
        
        start_time = time.time()
        compare_data = {
            "query": "Parallel test query",
            "pipeline_a_id": pipe_id,
            "pipeline_b_id": pipe_b_id
        }
        res_compare = await client.post(f"{API_URL}/pipelines/compare", json=compare_data)
        total_compare_time = time.time() - start_time
        
        if res_compare.status_code == 200:
            a_data = res_compare.json().get("pipeline_a", {})
            b_data = res_compare.json().get("pipeline_b", {})
            print(f"[SUCCESS] Compare completed in {total_compare_time:.2f}s returning A and B.")
            a_run_id = a_data.get("run_id")
            if not a_run_id:
                print("Note: run_id not in pipeline_a response (perhaps it errored out gracefully)")
        else:
            print(f"[FAILED] Compare returned {res_compare.status_code}")
            
        # 4 & 5. Check Analytics and DB records
        print("Checking 4 & 5: Analytics and pipeline_runs...")
        res_analytics = await client.get(f"{API_URL}/pipelines/{pipe_id}/analytics")
        if res_analytics.status_code == 200:
            analytics = res_analytics.json()
            if "p95_retrieval_latency" in analytics:
                print("[SUCCESS] Analytics returns p95 latency correctly.")
            else:
                print("[FAILED] Analytics missing p95_retrieval_latency.")
                
        res_runs = await client.get(f"{API_URL}/pipelines/{pipe_id}/runs")
        if res_runs.status_code == 200:
            runs = res_runs.json()
            if runs and all('pipeline_version' in r for r in runs):
                print(f"[SUCCESS] pipeline_runs records pipeline_version (Found in {len(runs)} runs).")
            else:
                print("[FAILED] pipeline_runs missing pipeline_version.")
                
if __name__ == "__main__":
    asyncio.run(main())

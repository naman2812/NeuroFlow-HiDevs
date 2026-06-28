import asyncio
import time
import json
import tiktoken
from uuid import UUID
from typing import AsyncGenerator, Dict, Any, List, Tuple

from backend.providers.client import NeuroFlowClient
from backend.providers.base import ChatMessage
from backend.providers.router import RoutingCriteria
from pipelines.generation.prompt_builder import build_prompt
from pipelines.generation.citations import parse_citations

class StreamingGenerator:
    def __init__(self, client: NeuroFlowClient, db_pool, redis_client):
        self.client = client
        self.db_pool = db_pool
        self.redis = redis_client
        self.tokenizer = tiktoken.get_encoding("cl100k_base")

    async def generate_stream(
        self, 
        run_id: str,
        pipeline_id: str,
        query: str, 
        query_type: str,
        assembled_context: Dict[str, Any],
        config: Dict[str, Any] = None
    ) -> AsyncGenerator[Tuple[str, List[Dict[str, Any]]], None]:
        
        prompt = build_prompt(query, assembled_context["context_data"], query_type)
        
        # Log assembled prompt to DB
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE pipeline_runs 
                SET prompt = $1, status = 'running'
                WHERE id = $2
                """,
                prompt, UUID(run_id)
            )
            
        messages = [ChatMessage(role="user", content=prompt)]
        
        task_type = "rag_generation"
        max_cost = 0.05
        temperature = 0.2
        if config and "generation" in config:
            gen_conf = config["generation"]
            if "model_routing" in gen_conf:
                task_type = gen_conf["model_routing"].get("task_type", task_type)
                max_cost = gen_conf["model_routing"].get("max_cost_per_call", max_cost)
            temperature = gen_conf.get("temperature", temperature)
            
        criteria = RoutingCriteria(task_type=task_type, max_cost_per_call=max_cost)
        
        # Override client stream_chat temperature if supported? The provider interface usually relies on kwargs.
        # We can pass temperature as kwargs to stream_chat in NeuroFlowClient.
        # Actually our NeuroFlowClient.stream_chat(messages, criteria, **kwargs) handles extra kwargs.
        stream_gen = await self.client.stream_chat(messages, criteria, temperature=temperature)
        
        start_time = time.time()
        
        full_response = []
        is_thinking = False
        buffer = ""
        think_content = ""
        clean_response = []
        
        # Stream from LLM
        async for chunk in stream_gen:
            full_response.append(chunk)
            buffer += chunk
            
            while True:
                if not is_thinking:
                    if "<think>" in buffer:
                        pre, post = buffer.split("<think>", 1)
                        if pre:
                            clean_response.append(pre)
                            yield (pre, [])
                        is_thinking = True
                        buffer = post
                    else:
                        last_lt = buffer.rfind("<")
                        if last_lt != -1 and "<think>".startswith(buffer[last_lt:]):
                            pre = buffer[:last_lt]
                            buffer = buffer[last_lt:]
                            if pre:
                                clean_response.append(pre)
                                yield (pre, [])
                            break
                        else:
                            pre = buffer
                            buffer = ""
                            if pre:
                                clean_response.append(pre)
                                yield (pre, [])
                            break
                else:
                    if "</think>" in buffer:
                        pre, post = buffer.split("</think>", 1)
                        think_content += pre
                        is_thinking = False
                        buffer = post
                    else:
                        last_lt = buffer.rfind("<")
                        if last_lt != -1 and "</think>".startswith(buffer[last_lt:]):
                            pre = buffer[:last_lt]
                            buffer = buffer[last_lt:]
                            think_content += pre
                            break
                        else:
                            think_content += buffer
                            buffer = ""
                            break
                            
        latency_ms = int((time.time() - start_time) * 1000)
        final_text = "".join(full_response)
        clean_text = "".join(clean_response)
        
        input_tokens = len(self.tokenizer.encode(prompt))
        output_tokens = len(self.tokenizer.encode(final_text))
        
        # Parse citations from clean text
        citations = parse_citations(clean_text, assembled_context)
        
        metadata_json = json.dumps({"think_content": think_content}) if think_content else "{}"
        
        # Log to DB
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE pipeline_runs 
                SET generation = $1, input_tokens = $2, output_tokens = $3, latency_ms = $4, status = 'complete', metadata = $5
                WHERE id = $6
                """,
                clean_text, input_tokens, output_tokens, latency_ms, metadata_json, UUID(run_id)
            )
            
        # Enqueue evaluation job (Task 37) asynchronously
        asyncio.create_task(self.redis.rpush("evaluation_queue", str(run_id)))
        
        # Final yield to send citations
        yield ("", citations)

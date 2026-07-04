import time
from typing import Any

import asyncpg
from opentelemetry import trace

from backend.monitoring.metrics import retrieval_latency
from backend.providers.client import NeuroFlowClient

from .context_assembler import ContextAssembler
from .models import RetrievalResult
from .query_processor import QueryProcessor
from .reranker import CrossEncoderReranker
from .retriever import Retriever

tracer = trace.get_tracer(__name__)


class RetrievalPipeline:
    def __init__(self, db_pool: asyncpg.Pool, client: NeuroFlowClient) -> None:
        self.query_processor = QueryProcessor(client)
        self.retriever = Retriever(db_pool, client)
        self.reranker = CrossEncoderReranker(client)
        self.context_assembler = ContextAssembler()

    async def retrieve(
        self, query: str, k: int = 10, token_budget: int = 4000, use_hyde: bool = False
    ) -> list[RetrievalResult]:
        """
        Mainly for evaluation script which expects a list of results.
        Executes up to reranking and returns the top K results.
        """
        # Step 1: Query Processing
        processed_query = await self.query_processor.process_query(query)

        # Step 2: Parallel Retrieval & Fusion
        # Pass k=60 to retriever to have enough candidates for reranking
        retrieved_results = await self.retriever.retrieve(
            processed_query, k=max(k, 60), use_hyde=use_hyde
        )

        # Step 3: Reranking
        # Take top 40 for reranking as per instructions
        reranked_results = await self.reranker.rerank(query, retrieved_results, top_n=40)

        return reranked_results[:k]

    async def get_context(
        self,
        query: str,
        config: dict[str, Any] | None = None,
        k: int = 10,
        token_budget: int = 4000,
        use_hyde: bool = False,
        pipeline_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Executes the full pipeline including context assembly.
        """
        start_time = time.time()
        with tracer.start_as_current_span("retrieval.pipeline") as span:
            if pipeline_id:
                span.set_attribute("pipeline_id", pipeline_id)
            if run_id:
                span.set_attribute("run_id", run_id)

            if config and "retrieval" in config:
                retrieval_conf = config["retrieval"]
                k = retrieval_conf.get("top_k_after_rerank", k)
                # We could use dense_k, query_expansion, etc. if supported
                if "query_expansion" in retrieval_conf:
                    use_hyde = retrieval_conf["query_expansion"]

            if config and "generation" in config:
                token_budget = config["generation"].get("max_context_tokens", token_budget)

            processed_query = await self.query_processor.process_query(query)
            retrieved_results = await self.retriever.retrieve(
                processed_query,
                k=max(k, 60),
                use_hyde=use_hyde,
                pipeline_id=pipeline_id,
                run_id=run_id,
            )
            reranked_results = await self.reranker.rerank(
                query, retrieved_results, top_n=40, pipeline_id=pipeline_id, run_id=run_id
            )

            final_results = reranked_results[:k]

            self.context_assembler.token_budget = token_budget
            assembled_context = self.context_assembler.assemble(
                final_results, pipeline_id=pipeline_id, run_id=run_id
            )

            span.set_attribute("final_chunks", len(final_results))

            duration = time.time() - start_time
            retrieval_latency.labels(strategy="full_pipeline").observe(duration)

            return {
                "query": processed_query.original_query,
                "expanded_queries": processed_query.expanded_queries,
                "query_type": processed_query.query_type,
                "context_data": assembled_context,
                "raw_results": final_results,
            }

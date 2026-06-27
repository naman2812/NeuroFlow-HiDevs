import asyncpg
from typing import Dict, Any, List

from backend.providers.client import NeuroFlowClient
from .query_processor import QueryProcessor
from .retriever import Retriever
from .reranker import CrossEncoderReranker
from .context_assembler import ContextAssembler
from .models import RetrievalResult

class RetrievalPipeline:
    def __init__(self, db_pool: asyncpg.Pool, client: NeuroFlowClient):
        self.query_processor = QueryProcessor(client)
        self.retriever = Retriever(db_pool, client)
        self.reranker = CrossEncoderReranker(client)
        self.context_assembler = ContextAssembler()
        
    async def retrieve(self, query: str, k: int = 10, token_budget: int = 4000, use_hyde: bool = False) -> List[RetrievalResult]:
        """
        Mainly for evaluation script which expects a list of results.
        Executes up to reranking and returns the top K results.
        """
        # Step 1: Query Processing
        processed_query = await self.query_processor.process_query(query)
        
        # Step 2: Parallel Retrieval & Fusion
        # Pass k=60 to retriever to have enough candidates for reranking
        retrieved_results = await self.retriever.retrieve(processed_query, k=max(k, 60), use_hyde=use_hyde)
        
        # Step 3: Reranking
        # Take top 40 for reranking as per instructions
        reranked_results = await self.reranker.rerank(query, retrieved_results, top_n=40)
        
        return reranked_results[:k]
        
    async def get_context(self, query: str, k: int = 10, token_budget: int = 4000, use_hyde: bool = False) -> Dict[str, Any]:
        """
        Executes the full pipeline including context assembly.
        """
        processed_query = await self.query_processor.process_query(query)
        retrieved_results = await self.retriever.retrieve(processed_query, k=max(k, 60), use_hyde=use_hyde)
        reranked_results = await self.reranker.rerank(query, retrieved_results, top_n=40)
        
        final_results = reranked_results[:k]
        
        self.context_assembler.token_budget = token_budget
        assembled_context = self.context_assembler.assemble(final_results)
        
        return {
            "query": processed_query.original_query,
            "expanded_queries": processed_query.expanded_queries,
            "query_type": processed_query.query_type,
            "context_data": assembled_context,
            "raw_results": final_results
        }

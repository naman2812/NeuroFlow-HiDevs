import json
import asyncio
import asyncpg
from typing import List, Dict, Any

from backend.providers.client import NeuroFlowClient
from .query_processor import ProcessedQuery
from .models import RetrievalResult
from .fusion import reciprocal_rank_fusion

class Retriever:
    def __init__(self, db_pool: asyncpg.Pool, client: NeuroFlowClient):
        self.db_pool = db_pool
        self.client = client
        
    async def retrieve(self, processed_query: ProcessedQuery, k: int = 20) -> List[RetrievalResult]:
        # Run three strategies in parallel
        results = await asyncio.gather(
            self._dense_retrieval(processed_query, k),
            self._sparse_retrieval(processed_query, k),
            self._metadata_retrieval(processed_query, k)
        )
        
        # Fuse results
        return reciprocal_rank_fusion(list(results))
        
    async def _dense_retrieval(self, processed_query: ProcessedQuery, k: int) -> List[RetrievalResult]:
        queries = [processed_query.original_query] + processed_query.expanded_queries
        
        # Embed all queries (original + expanded) in one shot
        embeddings = await self.client.embed(queries)
        
        results_list = []
        
        async with self.db_pool.acquire() as conn:
            for emb in embeddings:
                rows = await conn.fetch(
                    """
                    SELECT id, document_id, content, metadata, embedding <=> $1::vector AS score
                    FROM chunks
                    ORDER BY embedding <=> $1::vector
                    LIMIT $2
                    """,
                    json.dumps(emb), k
                )
                
                for row in rows:
                    results_list.append(
                        RetrievalResult(
                            chunk_id=str(row['id']),
                            document_id=str(row['document_id']),
                            content=row['content'],
                            metadata=json.loads(row['metadata']) if isinstance(row['metadata'], str) else row['metadata'],
                            score=1.0 - float(row['score']) # convert distance to similarity roughly
                        )
                    )
        
        unique_results = {}
        for r in results_list:
            if r.chunk_id not in unique_results or r.score > unique_results[r.chunk_id].score:
                unique_results[r.chunk_id] = r
                
        sorted_results = sorted(unique_results.values(), key=lambda x: x.score, reverse=True)[:k]
        return sorted_results
        
    async def _sparse_retrieval(self, processed_query: ProcessedQuery, k: int) -> List[RetrievalResult]:
        queries = [processed_query.original_query] + processed_query.expanded_queries
        results_list = []
        
        async with self.db_pool.acquire() as conn:
            for q in queries:
                rows = await conn.fetch(
                    """
                    SELECT id, document_id, content, metadata,
                           ts_rank_cd(to_tsvector('english', content), plainto_tsquery('english', $1)) AS score
                    FROM chunks
                    WHERE to_tsvector('english', content) @@ plainto_tsquery('english', $1)
                    ORDER BY score DESC
                    LIMIT $2
                    """,
                    q, k
                )
                
                for row in rows:
                    results_list.append(
                        RetrievalResult(
                            chunk_id=str(row['id']),
                            document_id=str(row['document_id']),
                            content=row['content'],
                            metadata=json.loads(row['metadata']) if isinstance(row['metadata'], str) else row['metadata'],
                            score=float(row['score'])
                        )
                    )
                    
        unique_results = {}
        for r in results_list:
            if r.chunk_id not in unique_results or r.score > unique_results[r.chunk_id].score:
                unique_results[r.chunk_id] = r
                
        sorted_results = sorted(unique_results.values(), key=lambda x: x.score, reverse=True)[:k]
        return sorted_results
            
    async def _metadata_retrieval(self, processed_query: ProcessedQuery, k: int) -> List[RetrievalResult]:
        if not processed_query.metadata_filters:
            return []
            
        embeddings = await self.client.embed([processed_query.original_query])
        emb = embeddings[0]
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, document_id, content, metadata, embedding <=> $2::vector AS distance
                FROM chunks
                WHERE metadata @> $1::jsonb
                ORDER BY embedding <=> $2::vector
                LIMIT $3
                """,
                json.dumps(processed_query.metadata_filters), json.dumps(emb), k
            )
            
            return [
                RetrievalResult(
                    chunk_id=str(row['id']),
                    document_id=str(row['document_id']),
                    content=row['content'],
                    metadata=json.loads(row['metadata']) if isinstance(row['metadata'], str) else row['metadata'],
                    score=1.0 - float(row['distance'])
                )
                for row in rows
            ]

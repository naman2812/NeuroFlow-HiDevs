from typing import List, Dict
from .models import RetrievalResult

def reciprocal_rank_fusion(
    result_lists: List[List[RetrievalResult]],
    k: int = 60
) -> List[RetrievalResult]:
    """
    Combines multiple retrieval lists using Reciprocal Rank Fusion.
    For each chunk, score = sum(1 / (k + rank)) across all lists.
    """
    chunk_scores: Dict[str, float] = {}
    chunk_map: Dict[str, RetrievalResult] = {}
    
    for result_list in result_lists:
        for rank, result in enumerate(result_list):
            chunk_id = result.chunk_id
            
            # Map chunk for later retrieval
            if chunk_id not in chunk_map:
                chunk_map[chunk_id] = result
                chunk_scores[chunk_id] = 0.0
                
            # Compute RRF score contribution
            # rank is 0-indexed, but the formula usually implies 1-indexed rank
            score_contribution = 1.0 / (k + (rank + 1))
            chunk_scores[chunk_id] += score_contribution
            
    # Create new results with fused scores
    fused_results = []
    for chunk_id, score in chunk_scores.items():
        original = chunk_map[chunk_id]
        # Create a copy with the new score
        fused = RetrievalResult(
            chunk_id=original.chunk_id,
            document_id=original.document_id,
            content=original.content,
            metadata=original.metadata,
            score=score
        )
        fused_results.append(fused)
        
    # Sort descending by score
    fused_results.sort(key=lambda x: x.score, reverse=True)
    return fused_results

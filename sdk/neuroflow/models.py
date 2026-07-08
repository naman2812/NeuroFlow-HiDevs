from typing import Any, List, Optional
from pydantic import BaseModel

class Document(BaseModel):
    document_id: str
    status: str
    duplicate: bool = False
    chunk_count: Optional[int] = None
    metadata: Optional[dict] = None

class QueryResult(BaseModel):
    run_id: str
    answer: str
    citations: List[Any] = []
    context_sources: List[dict] = []

class EvaluationResult(BaseModel):
    id: str
    run_id: str
    pipeline_name: str
    query: str
    faithfulness: float
    answer_relevance: float
    context_precision: float
    context_recall: float
    overall_score: float
    evaluated_at: str
    status: str = "complete"

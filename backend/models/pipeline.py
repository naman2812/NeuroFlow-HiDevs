from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any
from uuid import UUID

class IngestionConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    chunking_strategy: str
    chunk_size_tokens: int
    chunk_overlap_tokens: int
    extractors_enabled: List[str]

class RetrievalConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dense_k: int
    sparse_k: int
    reranker: str
    top_k_after_rerank: int
    query_expansion: bool
    metadata_filters_enabled: bool

class GenerationRoutingConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task_type: str
    max_cost_per_call: float

class GenerationConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model_routing: GenerationRoutingConfig
    max_context_tokens: int
    temperature: float
    system_prompt_variant: str

class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    auto_evaluate: bool
    training_threshold: float

from pydantic import BaseModel, ConfigDict, Field

class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(..., max_length=100)
    description: str
    ingestion: IngestionConfig
    retrieval: RetrievalConfig
    generation: GenerationConfig
    evaluation: EvaluationConfig

class PipelineCreate(BaseModel):
    config: PipelineConfig

class PipelineUpdate(BaseModel):
    config: PipelineConfig

class PipelineResponse(BaseModel):
    id: UUID
    name: str
    version: int
    status: str
    config: Any
    created_at: Any
    
    class Config:
        from_attributes = True

class PipelineRunResponse(BaseModel):
    id: UUID
    pipeline_id: UUID
    pipeline_version: Optional[int]
    query: str
    generation: Optional[str]
    retrieval_latency_ms: Optional[int]
    latency_ms: Optional[int]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    model_used: Optional[str]
    status: str
    created_at: Any
    
    class Config:
        from_attributes = True

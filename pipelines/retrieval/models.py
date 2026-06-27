from pydantic import BaseModel
from typing import Dict, Any, List, Optional

class RetrievalResult(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    metadata: Dict[str, Any]
    score: float
    
    class Config:
        # Allow extra fields if needed, but primarily use the defined ones
        extra = "allow"

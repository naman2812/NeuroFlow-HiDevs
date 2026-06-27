import tiktoken
from typing import List, Dict, Any
from .models import RetrievalResult

class ContextAssembler:
    def __init__(self, token_budget: int = 4000, model_name: str = "gpt-3.5-turbo"):
        self.token_budget = token_budget
        try:
            self.encoding = tiktoken.encoding_for_model(model_name)
        except Exception:
            # Fallback
            self.encoding = tiktoken.get_encoding("cl100k_base")
            
    def assemble(self, results: List[RetrievalResult]) -> Dict[str, Any]:
        context_str = ""
        current_tokens = 0
        chunks_used = []
        sources = []
        
        for i, result in enumerate(results):
            # Try to get filename from metadata, fallback to document_id
            doc_name = result.metadata.get('filename', f'doc_{result.document_id}')
            
            # Get page or section if available
            page = result.metadata.get('page_number')
            if page:
                source_header = f"[Source {len(sources)+1} — {doc_name}, page {page}]\n"
            else:
                source_header = f"[Source {len(sources)+1} — {doc_name}]\n"
                
            chunk_text = f"{source_header}{result.content}\n\n"
            
            # Count tokens
            chunk_tokens = len(self.encoding.encode(chunk_text))
            
            # If it fits, add it. Never truncate mid-sentence.
            if current_tokens + chunk_tokens <= self.token_budget:
                context_str += chunk_text
                current_tokens += chunk_tokens
                chunks_used.append(result.chunk_id)
                sources.append({"document_id": result.document_id, "filename": doc_name, "page": page})
            else:
                # If a chunk doesn't fit, skip it entirely to avoid mid-sentence truncation
                continue
                
        return {
            "context": context_str.strip(),
            "chunks_used": chunks_used,
            "total_tokens": current_tokens,
            "sources": sources
        }

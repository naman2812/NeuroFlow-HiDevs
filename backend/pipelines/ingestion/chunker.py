import tiktoken
import re
import numpy as np
from typing import List, Dict, Any
from dataclasses import dataclass
from .extractors import ExtractedPage
from backend.providers.client import NeuroFlowClient

@dataclass
class Chunk:
    content: str
    chunk_index: int
    token_count: int
    metadata: Dict[str, Any]

class Chunker:
    def __init__(self, client: NeuroFlowClient = None):
        self.encoder = tiktoken.get_encoding("cl100k_base")
        self.client = client

    async def chunk_document(self, pages: List[ExtractedPage], source_type: str) -> List[Chunk]:
        if not pages:
            return []
            
        # Determine strategy
        has_headings = any(p.metadata.get("level") for p in pages)
        is_table = all(p.content_type == "table" for p in pages)
        is_large_pdf = source_type == "pdf" and len(pages) > 50

        if is_table:
            strategy = "fixed_size"
        elif source_type == "docx" and has_headings:
            strategy = "hierarchical"
        elif is_large_pdf:
            strategy = "semantic"
        else:
            strategy = "fixed_size"

        if strategy == "fixed_size":
            return self._chunk_fixed_size(pages)
        elif strategy == "hierarchical":
            return self._chunk_hierarchical(pages)
        elif strategy == "semantic":
            return await self._chunk_semantic(pages)
        else:
            return self._chunk_fixed_size(pages)

    def _split_into_sentences(self, text: str) -> List[str]:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _chunk_fixed_size(self, pages: List[ExtractedPage]) -> List[Chunk]:
        chunks = []
        chunk_idx = 0
        target_tokens = 512
        overlap_tokens = 64
        
        full_text = "\n\n".join(p.content for p in pages)
        sentences = self._split_into_sentences(full_text)
        
        current_chunk_sentences = []
        current_tokens = 0
        
        for sentence in sentences:
            tokens = len(self.encoder.encode(sentence))
            
            if current_tokens + tokens > target_tokens and current_chunk_sentences:
                chunk_text = " ".join(current_chunk_sentences)
                chunks.append(Chunk(
                    content=chunk_text,
                    chunk_index=chunk_idx,
                    token_count=current_tokens,
                    metadata={"strategy": "fixed_size"}
                ))
                chunk_idx += 1
                
                # Keep overlap
                overlap_sentences = []
                overlap_count = 0
                for s in reversed(current_chunk_sentences):
                    s_toks = len(self.encoder.encode(s))
                    if overlap_count + s_toks <= overlap_tokens:
                        overlap_sentences.insert(0, s)
                        overlap_count += s_toks
                    else:
                        break
                        
                current_chunk_sentences = overlap_sentences
                current_tokens = overlap_count
                
            current_chunk_sentences.append(sentence)
            current_tokens += tokens
            
        if current_chunk_sentences:
            chunk_text = " ".join(current_chunk_sentences)
            chunks.append(Chunk(
                content=chunk_text,
                chunk_index=chunk_idx,
                token_count=current_tokens,
                metadata={"strategy": "fixed_size"}
            ))
            
        return chunks

    def _chunk_hierarchical(self, pages: List[ExtractedPage]) -> List[Chunk]:
        chunks = []
        chunk_idx = 0
        current_parent_h1 = None
        
        for page in pages:
            level = page.metadata.get("level", "p")
            section = page.metadata.get("section", "")
            
            if level == "h1":
                current_parent_h1 = section
                parent_id = None
            else:
                parent_id = current_parent_h1
                
            token_count = len(self.encoder.encode(page.content))
            chunks.append(Chunk(
                content=page.content,
                chunk_index=chunk_idx,
                token_count=token_count,
                metadata={
                    "strategy": "hierarchical",
                    "level": level,
                    "section": section,
                    "parent_section": parent_id
                }
            ))
            chunk_idx += 1
            
        return chunks

    async def _chunk_semantic(self, pages: List[ExtractedPage]) -> List[Chunk]:
        if not self.client:
            # Fallback
            return self._chunk_fixed_size(pages)
            
        full_text = "\n\n".join(p.content for p in pages)
        sentences = self._split_into_sentences(full_text)
        if not sentences:
            return []
            
        # Prevent huge payloads by batching embed calls if necessary
        embeddings = []
        batch_size = 100
        for i in range(0, len(sentences), batch_size):
            batch = sentences[i:i+batch_size]
            emb_batch = await self.client.embed(batch)
            embeddings.extend(emb_batch)
        
        chunks = []
        chunk_idx = 0
        current_chunk_sentences = [sentences[0]]
        
        for i in range(1, len(sentences)):
            emb1 = np.array(embeddings[i-1])
            emb2 = np.array(embeddings[i])
            
            norm1 = np.linalg.norm(emb1)
            norm2 = np.linalg.norm(emb2)
            if norm1 == 0 or norm2 == 0:
                similarity = 1.0
            else:
                similarity = np.dot(emb1, emb2) / (norm1 * norm2)
            
            if similarity < 0.7:
                chunk_text = " ".join(current_chunk_sentences)
                chunks.append(Chunk(
                    content=chunk_text,
                    chunk_index=chunk_idx,
                    token_count=len(self.encoder.encode(chunk_text)),
                    metadata={"strategy": "semantic"}
                ))
                chunk_idx += 1
                current_chunk_sentences = [sentences[i]]
            else:
                current_chunk_sentences.append(sentences[i])
                
        if current_chunk_sentences:
            chunk_text = " ".join(current_chunk_sentences)
            chunks.append(Chunk(
                content=chunk_text,
                chunk_index=chunk_idx,
                token_count=len(self.encoder.encode(chunk_text)),
                metadata={"strategy": "semantic"}
            ))
            
        return chunks

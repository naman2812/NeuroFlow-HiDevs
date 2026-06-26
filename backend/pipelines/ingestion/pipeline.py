import json
import logging
import asyncpg
from typing import List
from opentelemetry import trace
from .extractors import extract_pdf, extract_docx, extract_image, extract_csv, extract_url
from .extractors import ExtractedPage
from .chunker import Chunker
from backend.providers.client import NeuroFlowClient

tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)

async def process_document_pipeline(
    db_pool: asyncpg.Pool, 
    client: NeuroFlowClient, 
    document_id: str, 
    file_path: str, 
    source_type: str
):
    with tracer.start_as_current_span("ingestion.process") as span:
        span.set_attribute("document_id", document_id)
        span.set_attribute("source_type", source_type)
        
        try:
            # 1. Extraction
            if source_type == "pdf":
                pages = extract_pdf(file_path)
            elif source_type == "docx":
                pages = extract_docx(file_path)
            elif source_type in ["image", "jpeg", "png", "webp", "jpg"]:
                pages = await extract_image(file_path, client)
            elif source_type == "csv":
                pages = extract_csv(file_path)
            elif source_type == "url":
                pages = await extract_url(file_path)  # file_path is actually the URL
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    pages = [ExtractedPage(page_number=1, content=f.read(), content_type="text", metadata={})]
                    
            span.set_attribute("page_count", len(pages))
            
            # 2. Chunking
            chunker = Chunker(client=client)
            chunks = await chunker.chunk_document(pages, source_type)
            span.set_attribute("chunk_count", len(chunks))
            
            # 3. Embed chunks
            texts = [c.content for c in chunks]
            embeddings = await client.embed(texts) if texts else []
            span.set_attribute("embedding_calls", 1 if embeddings else 0)
            
            # 4. DB Persistence
            async with db_pool.acquire() as conn:
                async with conn.transaction():
                    for chunk, emb in zip(chunks, embeddings):
                        await conn.execute(
                            """
                            INSERT INTO chunks (document_id, content, embedding, chunk_index, token_count, metadata)
                            VALUES ($1, $2, $3, $4, $5, $6)
                            """,
                            document_id, chunk.content, json.dumps(emb), chunk.chunk_index, chunk.token_count, json.dumps(chunk.metadata)
                        )
                        
                    # Aggregate metadata
                    doc_metadata = {}
                    for p in pages:
                        doc_metadata.update(p.metadata)
                        
                    # Update document status
                    await conn.execute(
                        "UPDATE documents SET status = 'complete', chunk_count = $1, metadata = $2 WHERE id = $3",
                        len(chunks), json.dumps(doc_metadata), document_id
                    )
                    
            logger.info(json.dumps({
                "event": "ingestion_complete",
                "document_id": str(document_id),
                "chunks": len(chunks),
                "tokens": sum(c.token_count for c in chunks)
            }))
            
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            async with db_pool.acquire() as conn:
                await conn.execute("UPDATE documents SET status = 'failed' WHERE id = $1", document_id)
            raise e

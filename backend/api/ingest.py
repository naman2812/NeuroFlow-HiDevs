import hashlib
import os
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from arq import create_pool
from arq.connections import RedisSettings
from backend.config import settings
from backend.db.pool import get_pool

router = APIRouter()

class URLIngestRequest(BaseModel):
    url: str

async def get_redis_pool():
    return await create_pool(RedisSettings(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password
    ))

UPLOAD_DIR = "/app/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/ingest")
async def ingest_document(
    request: Request,
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    redis = Depends(get_redis_pool)
):
    # Determine type
    source_type = None
    file_bytes = None
    content_hash = None
    filename = None
    
    if file:
        ext = file.filename.split('.')[-1].lower()
        if ext in ["pdf", "docx", "csv", "pptx"]:
            source_type = ext
        elif ext in ["jpeg", "jpg", "png", "webp"]:
            source_type = "image"
        elif ext in ["txt", "md"]:
            source_type = "text"
        else:
            raise HTTPException(400, "Unsupported file type")
            
        file_bytes = await file.read()
        if len(file_bytes) > 100 * 1024 * 1024:
            raise HTTPException(400, "File too large (max 100MB)")
            
        content_hash = hashlib.sha256(file_bytes).hexdigest()
        filename = file.filename
        
    else:
        # Check if json body was passed
        try:
            body = await request.json()
            url = body.get("url")
        except:
            pass
            
        if url:
            source_type = "url"
            content_hash = hashlib.sha256(url.encode()).hexdigest()
            filename = url
            file_bytes = None
        else:
            raise HTTPException(400, "Must provide file or url")
            
    db_pool = get_pool()
    
    # Check deduplication
    async with db_pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id, status FROM documents WHERE content_hash = $1", content_hash
        )
        if existing:
            return {"document_id": str(existing["id"]), "status": existing["status"], "duplicate": True}
            
        doc_id = str(uuid.uuid4())
        
        # Save file to shared volume if not URL
        if file_bytes:
            file_path = os.path.join(UPLOAD_DIR, f"{doc_id}_{filename}")
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            worker_source_type = ext if source_type == "image" else source_type
        else:
            file_path = url # for url extractor, we just pass the URL
            worker_source_type = "url"

        await conn.execute(
            """
            INSERT INTO documents (id, filename, source_type, content_hash, status)
            VALUES ($1, $2, $3, $4, 'queued')
            """,
            doc_id, filename, source_type, content_hash
        )
        
    # Enqueue job
    await redis.enqueue_job("process_document", doc_id, file_path, worker_source_type)
    
    return {"document_id": doc_id, "status": "queued", "duplicate": False}

@router.get("/documents/{document_id}")
async def get_document_status(document_id: str, request: Request):
    db_pool = get_pool()
    
    try:
        uuid.UUID(document_id)
    except:
        raise HTTPException(400, "Invalid document ID")
        
    async with db_pool.acquire() as conn:
        doc = await conn.fetchrow(
            "SELECT status, chunk_count, metadata FROM documents WHERE id = $1",
            document_id
        )
        
    if not doc:
        raise HTTPException(404, "Document not found")
        
    return {
        "status": doc["status"],
        "chunk_count": doc["chunk_count"],
        "metadata": doc["metadata"]
    }

import asyncio
import uuid
import structlog
from datetime import datetime, timedelta
from backend.db.pool import create_pool, close_pool, get_pool
from backend.db.retention import run_data_retention_policy
from backend.config import settings

logger = structlog.get_logger()

async def test_retention():
    await create_pool()
    pool = get_pool()
    
    async with pool.acquire() as conn:
        # 1. Insert a dummy pipeline
        pipeline_id = uuid.uuid4()
        await conn.execute("INSERT INTO pipelines (id, name, config) VALUES ($1, $2, '{}')", pipeline_id, str(pipeline_id))
        
        # 2. Insert fake old pipeline_run (should be deleted)
        old_run_id_deleted = uuid.uuid4()
        await conn.execute(
            "INSERT INTO pipeline_runs (id, pipeline_id, query, status, created_at) VALUES ($1, $2, 'test', 'complete', NOW() - INTERVAL '100 days')",
            old_run_id_deleted, pipeline_id
        )
        
        # 3. Insert fake old pipeline_run with flagged metadata (should NOT be deleted)
        old_run_id_flagged = uuid.uuid4()
        await conn.execute(
            "INSERT INTO pipeline_runs (id, pipeline_id, query, status, created_at, metadata) VALUES ($1, $2, 'test', 'complete', NOW() - INTERVAL '100 days', '{\"flagged\": \"true\"}')",
            old_run_id_flagged, pipeline_id
        )
        
        # 4. Insert fake old evaluation (should be deleted)
        old_eval_run_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO pipeline_runs (id, pipeline_id, query, status) VALUES ($1, $2, 'test', 'complete')",
            old_eval_run_id, pipeline_id
        )
        await conn.execute(
            "INSERT INTO evaluations (run_id, evaluated_at) VALUES ($1, NOW() - INTERVAL '190 days')",
            old_eval_run_id
        )
        
        # 5. Insert fake archived document and chunks (should be deleted)
        doc_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO documents (id, filename, source_type, content_hash, status) VALUES ($1, 'test.txt', 'text', $1::text, 'archived')",
            doc_id
        )
        chunk_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO chunks (id, document_id, content, chunk_index, token_count) VALUES ($1, $2, 'chunk', 0, 1)",
            chunk_id, doc_id
        )

    # Run retention policy
    await run_data_retention_policy()

    # Verify
    async with pool.acquire() as conn:
        run_count = await conn.fetchval("SELECT COUNT(*) FROM pipeline_runs WHERE id = $1", old_run_id_deleted)
        flagged_run_count = await conn.fetchval("SELECT COUNT(*) FROM pipeline_runs WHERE id = $1", old_run_id_flagged)
        eval_count = await conn.fetchval("SELECT COUNT(*) FROM evaluations WHERE run_id = $1", old_eval_run_id)
        chunk_count = await conn.fetchval("SELECT COUNT(*) FROM chunks WHERE id = $1", chunk_id)

        print(f"Old run deleted: {run_count == 0}")
        print(f"Flagged run preserved: {flagged_run_count == 1}")
        print(f"Old eval deleted: {eval_count == 0}")
        print(f"Archived chunk deleted: {chunk_count == 0}")

    await close_pool()

if __name__ == "__main__":
    asyncio.run(test_retention())

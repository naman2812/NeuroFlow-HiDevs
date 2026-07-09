import asyncio
import asyncpg
import sys
import logging
logger = logging.getLogger(__name__)



DATABASE_URL = "postgresql://postgres:tKmPndBAhanmjCQsaXwCOimxNejMDtMR@yamabiko.proxy.rlwy.net:36426/railway"

async def main():
    logger.info(f"Connecting to database...")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # We need to install pgvector extension first
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        
        logger.info("Running schema...")
        with open('infra/init/001_schema.sql', 'r', encoding='utf-8') as f:
            await conn.execute(f.read())
            
        logger.info("Running RLS...")
        with open('infra/init/002_rls.sql', 'r', encoding='utf-8') as f:
            await conn.execute(f.read())
            
        logger.info("Database initialized successfully!")
    except Exception as e:
        logger.info(f"Failed to initialize: {e}")
        sys.exit(1)
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())

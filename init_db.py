import asyncio
import asyncpg
import sys

DATABASE_URL = "postgresql://postgres:tKmPndBAhanmjCQsaXwCOimxNejMDtMR@yamabiko.proxy.rlwy.net:36426/railway"

async def main():
    print(f"Connecting to database...")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # We need to install pgvector extension first
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        
        print("Running schema...")
        with open('infra/init/001_schema.sql', 'r', encoding='utf-8') as f:
            await conn.execute(f.read())
            
        print("Running RLS...")
        with open('infra/init/002_rls.sql', 'r', encoding='utf-8') as f:
            await conn.execute(f.read())
            
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Failed to initialize: {e}")
        sys.exit(1)
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import asyncpg
import sys

DATABASE_URL = "postgresql://postgres:tKmPndBAhanmjCQsaXwCOimxNejMDtMR@yamabiko.proxy.rlwy.net:36426/railway"

async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        pipeline_id = await conn.fetchval("SELECT id FROM pipelines LIMIT 1;")
        if not pipeline_id:
            print("No pipeline exists. Creating one...")
            pipeline_id = await conn.fetchval("INSERT INTO pipelines (name, config) VALUES ('Default', '{}') RETURNING id;")
        print(f"PIPELINE_ID={pipeline_id}")
    except Exception as e:
        print(f"Failed: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())

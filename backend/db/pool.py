import asyncpg
from backend.config import settings

pool = None

async def create_pool():
    global pool
    pool = await asyncpg.create_pool(dsn=settings.database_url)

async def close_pool():
    global pool
    if pool:
        await pool.close()
        pool = None

def get_pool():
    return pool

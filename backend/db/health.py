import asyncpg
import redis.asyncio as redis
import httpx
from backend.config import settings
from backend.db.pool import get_pool

async def check_postgres() -> bool:
    pool = get_pool()
    if not pool:
        return False
    try:
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception:
        return False

async def check_redis() -> bool:
    try:
        r = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password
        )
        await r.ping()
        await r.close()
        return True
    except Exception:
        return False

async def check_mlflow() -> bool:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.mlflow_uri}/health")
            # MLflow returns 200 on health
            return response.status_code == 200
    except Exception:
        return False

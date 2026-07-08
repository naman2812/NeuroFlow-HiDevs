import asyncio
import redis.asyncio as aioredis
import logging
logger = logging.getLogger(__name__)


async def check():
    r = aioredis.from_url('redis://:neuroflow_redis_secure@localhost:6379', decode_responses=True)
    logger.info(await r.hgetall('router:models'))
    await r.aclose()
asyncio.run(check())

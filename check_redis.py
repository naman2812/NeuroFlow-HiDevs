import asyncio
import redis.asyncio as aioredis
async def check():
    r = aioredis.from_url('redis://:neuroflow_redis_secure@localhost:6379', decode_responses=True)
    print(await r.hgetall('router:models'))
    await r.aclose()
asyncio.run(check())

import asyncio
import time
import httpx
import redis.asyncio as aioredis
from backend.resilience.circuit_breaker import CircuitBreaker, CircuitOpenError
from backend.resilience.rate_limiter import wait_for_token
from backend.resilience.timeouts import TimeoutManager

async def test_circuit_breaker():
    print("Testing Circuit Breaker...")
    r = aioredis.from_url("redis://:devpassword@localhost:6379", decode_responses=True)
    await r.flushall()
    
    cb = CircuitBreaker("test_provider", failure_threshold=5, recovery_timeout=2, half_open_max_calls=2)
    cb.redis = r
    
    # 1. 5 consecutive failures
    for i in range(5):
        try:
            async with cb:
                raise ValueError("Simulated failure")
        except ValueError:
            pass
            
    # Now it should be open
    try:
        async with cb:
            pass
        print("FAIL: Circuit did not open after 5 failures")
        return
    except CircuitOpenError:
        print("PASS: Circuit opened after 5 failures")
        
    # Wait for recovery timeout
    print("Waiting for recovery timeout (2.1s)...")
    await asyncio.sleep(2.1)
    
    # Half-open allows exactly 2 calls
    try:
        async with cb:
            pass # 1st success
        async with cb:
            pass # 2nd success
    except CircuitOpenError:
        print("FAIL: Half-open blocked calls prematurely")
        return
        
    print("PASS: Circuit half-open allowed calls through and closed")

async def test_rate_limiter():
    print("Testing Rate Limiter...")
    r = aioredis.from_url("redis://:devpassword@localhost:6379", decode_responses=True)
    await r.flushall()
    
    # We will test token bucket wait_for_token
    # Capacity 5, refill rate 1/s
    for i in range(5):
        await wait_for_token("test:tokens", 5, 1.0)
        
    start = time.time()
    # 6th call should wait ~1s
    await wait_for_token("test:tokens", 5, 1.0)
    end = time.time()
    
    if end - start >= 0.9:
        print("PASS: Rate limiter successfully waited for tokens")
    else:
        print(f"FAIL: Rate limiter did not wait long enough ({end-start}s)")

async def test_health_degraded():
    print("Testing Health Check Degraded State...")
    r = aioredis.from_url("redis://:devpassword@localhost:6379", decode_responses=True)
    await r.flushall()
    
    # Manually open a circuit
    await r.set("circuit:openai:state", "open")
    await r.set("circuit:openai:opened_at", str(time.time()))
    
    async with httpx.AsyncClient() as client:
        resp = await client.get("http://localhost:8000/health")
        if resp.status_code == 200:
            data = resp.json()
            if data["status"] == "degraded":
                print("PASS: Health check reports degraded when circuit open")
            else:
                print(f"FAIL: Health check status is {data['status']}")
        else:
            print(f"FAIL: Health check failed with {resp.status_code}")

async def test_backpressure():
    print("Testing Backpressure...")
    r = aioredis.from_url("redis://:devpassword@localhost:6379", decode_responses=True)
    
    # Push 101 items to queue:ingest
    for i in range(101):
        await r.lpush("queue:ingest", "dummy")
        
    async with httpx.AsyncClient() as client:
        resp = await client.post("http://localhost:8000/ingest", data={"url": "http://example.com"})
        if resp.status_code == 503:
            data = resp.json()
            if data.get("error") == "ingestion_queue_full":
                print("PASS: Ingest returns 503 when queue > 100")
            else:
                print("FAIL: Wrong JSON returned for 503")
        else:
            print(f"FAIL: Ingest returned {resp.status_code} instead of 503")
            
    await r.delete("queue:ingest")

async def main():
    await test_circuit_breaker()
    await test_rate_limiter()
    await test_health_degraded()
    await test_backpressure()

if __name__ == "__main__":
    asyncio.run(main())

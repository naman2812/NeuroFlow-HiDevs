import asyncio
import httpx
from uuid import uuid4

API_URL = "http://localhost:8000"

async def main():
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Get pipelines
        res = await client.get(f"{API_URL}/pipelines")
        pipelines = res.json()
        
        if pipelines:
            p_id = pipelines[0]["id"]
            print(f"Testing suggestions for pipeline {p_id}")
            res_sug = await client.get(f"{API_URL}/pipelines/{p_id}/suggestions")
            print("Status:", res_sug.status_code)
            print("Suggestions:", res_sug.json())
        else:
            print("No pipelines found to test.")

if __name__ == "__main__":
    asyncio.run(main())

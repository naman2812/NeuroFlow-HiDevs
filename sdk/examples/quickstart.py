import asyncio
import os
from neuroflow import NeuroFlowClient

async def main():
    # Replace with your actual live deployment URL and API Key
    client = NeuroFlowClient(
        base_url=os.getenv("NEUROFLOW_URL", "http://localhost:8000"),
        api_key=os.getenv("NEUROFLOW_API_KEY", "test-token")
    )
    
    pipeline_id = "123e4567-e89b-12d3-a456-426614174000"

    print("1. Ingesting Wikipedia page via URL...")
    doc = await client.ingest_url(
        url="https://en.wikipedia.org/wiki/Artificial_intelligence", 
        pipeline_id=pipeline_id
    )
    print(f"Document Ingested! ID: {doc.document_id} | Status: {doc.status}")

    print("\n2. Running streaming query...")
    print("Response: ", end="")
    async for token in client.query(
        query="What is artificial intelligence?", 
        pipeline_id=pipeline_id, 
        stream=True
    ):
        print(token, end="", flush=True)
    
    print("\n\nDone!")
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())

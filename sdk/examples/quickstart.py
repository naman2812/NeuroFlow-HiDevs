import asyncio
import os
from neuroflow import NeuroFlowClient
import logging
logger = logging.getLogger(__name__)



async def main():
    # Replace with your actual live deployment URL and API Key
    client = NeuroFlowClient(
        base_url=os.getenv("NEUROFLOW_URL", "http://localhost:8000"),
        api_key=os.getenv("NEUROFLOW_API_KEY", "test-token")
    )
    
    pipeline_id = "123e4567-e89b-12d3-a456-426614174000"

    logger.info("1. Ingesting Wikipedia page via URL...")
    doc = await client.ingest_url(
        url="https://en.wikipedia.org/wiki/Artificial_intelligence", 
        pipeline_id=pipeline_id
    )
    logger.info(f"Document Ingested! ID: {doc.document_id} | Status: {doc.status}")

    logger.info("\n2. Running streaming query...")
    logger.info("Response: ", end="")
    async for token in client.query(
        query="What is artificial intelligence?", 
        pipeline_id=pipeline_id, 
        stream=True
    ):
        logger.info(token, end="", flush=True)
    
    logger.info("\n\nDone!")
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())

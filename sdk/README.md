# NeuroFlow Python SDK

A minimal but complete Python SDK that wraps the NeuroFlow API.

## Quickstart

```python
import asyncio
from neuroflow import NeuroFlowClient

async def main():
    client = NeuroFlowClient("http://localhost:8000", api_key="your-token")
    doc = await client.ingest_url("https://example.com", pipeline_id="uuid")
    print(f"Ingested document: {doc.document_id}")
    
    async for token in client.query("What is this?", pipeline_id="uuid", stream=True):
        print(token, end="", flush=True)

asyncio.run(main())
```

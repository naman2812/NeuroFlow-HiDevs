import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional, Union

import httpx
from httpx_sse import aconnect_sse

from .models import Document, EvaluationResult, QueryResult


class NeuroFlowClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {self.api_key}"}
        self.client = httpx.AsyncClient(headers=self.headers, timeout=30.0)

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self.base_url}{path}"
        max_retries = 5
        base_delay = 1.0

        for attempt in range(max_retries):
            response = await self.client.request(method, url, **kwargs)
            if response.status_code == 429:
                if attempt == max_retries - 1:
                    response.raise_for_status()
                delay = base_delay * (2 ** attempt)
                await asyncio.sleep(delay)
                continue
            response.raise_for_status()
            return response
            
        raise Exception("Max retries exceeded")

    async def ingest_file(self, file_path: Union[str, Path], pipeline_id: str = None) -> Document:
        """Upload and ingest a file. Waits for ingestion to complete."""
        path = Path(file_path)
        with open(path, "rb") as f:
            files = {"file": (path.name, f, "application/octet-stream")}
            data = {"pipeline_id": pipeline_id} if pipeline_id else {}
            response = await self._request("POST", "/ingest/file", files=files, data=data)
            
        doc_data = response.json()
        doc = Document(document_id=doc_data["document_id"], status=doc_data["status"], duplicate=doc_data.get("duplicate", False))
        
        return await self._poll_ingestion(doc.document_id)

    async def ingest_url(self, url: str, pipeline_id: str = None) -> Document:
        """Ingest a URL. Waits for ingestion to complete."""
        data = {"url": url}
        if pipeline_id:
            data["pipeline_id"] = pipeline_id
            
        response = await self._request("POST", "/ingest/url", json=data)
        doc_data = response.json()
        doc = Document(document_id=doc_data["document_id"], status=doc_data["status"], duplicate=doc_data.get("duplicate", False))
        
        return await self._poll_ingestion(doc.document_id)

    async def _poll_ingestion(self, document_id: str) -> Document:
        """Polls the status endpoint until ingestion is complete."""
        while True:
            response = await self._request("GET", f"/documents/{document_id}")
            data = response.json()
            if data["status"] == "complete":
                return Document(document_id=document_id, **data)
            elif data["status"] == "error":
                raise Exception(f"Ingestion failed for document {document_id}")
            await asyncio.sleep(2.0)

    async def query(self, query: str, pipeline_id: str, stream: bool = False) -> Union[QueryResult, AsyncGenerator[str, None]]:
        """Run a RAG query. If stream=True, returns an async generator of tokens."""
        payload = {
            "query": query,
            "pipeline_id": pipeline_id,
            "stream": stream
        }
        
        response = await self._request("POST", "/query", json=payload)
        data = response.json()
        
        if not stream:
            return QueryResult(**data)
            
        run_id = data["run_id"]
        
        async def stream_generator() -> AsyncGenerator[str, None]:
            url = f"{self.base_url}/query/{run_id}/stream"
            max_retries = 5
            base_delay = 1.0
            
            for attempt in range(max_retries):
                try:
                    async with aconnect_sse(self.client, "GET", url) as event_source:
                        async for event in event_source.aiter_sse():
                            if event.event == "message":
                                event_data = json.loads(event.data)
                                if event_data.get("type") == "token":
                                    yield event_data["delta"]
                                elif event_data.get("type") == "error":
                                    raise Exception(event_data["message"])
                                elif event_data.get("type") == "done":
                                    return
                    return
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
                        continue
                    raise

        return stream_generator()

    async def get_evaluation(self, run_id: str, wait: bool = True) -> EvaluationResult:
        """Get evaluation results for a query run."""
        while True:
            try:
                response = await self._request("GET", f"/evaluations/{run_id}")
                data = response.json()
                return EvaluationResult(**data)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404 and wait:
                    await asyncio.sleep(5.0)
                    continue
                raise

    async def list_pipelines(self) -> List[dict]:
        response = await self._request("GET", "/pipelines")
        return response.json()

    async def create_pipeline(self, config: dict) -> dict:
        response = await self._request("POST", "/pipelines", json=config)
        return response.json()
        
    async def close(self):
        await self.client.aclose()

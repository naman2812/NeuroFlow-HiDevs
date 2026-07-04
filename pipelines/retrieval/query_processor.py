import json
from typing import Any

from pydantic import BaseModel

from backend.providers.base import ChatMessage
from backend.providers.client import NeuroFlowClient
from backend.providers.router import RoutingCriteria


class ProcessedQuery(BaseModel):
    original_query: str
    expanded_queries: list[str]
    metadata_filters: dict[str, Any]
    query_type: str
    hypothetical_document: str | None = None


class QueryProcessor:
    def __init__(self, client: NeuroFlowClient) -> None:
        self.client = client

    async def process_query(self, query: str) -> ProcessedQuery:
        system_prompt = """
You are an expert search query processing engine. Analyze the user's query and output a JSON object with the following fields:
1. "expanded_queries": A list of 2-3 alternative phrasings or expansions of the query to improve search recall. Use different vocabulary but keep the same semantic meaning.
2. "metadata_filters": A JSON object containing any explicit or implicit filters mentioned in the query (e.g., {"year": 2023, "topic": "climate"}). If none, output an empty object {}.
3. "query_type": Classify the query into exactly one of: "factual", "analytical", "comparative", or "procedural".
4. "hypothetical_document": A detailed hypothetical passage or paragraph that directly answers the user's query. Write it in the tone and style of the documents that might contain the answer.

Output ONLY valid JSON.
"""  # noqa: E501

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=query),
        ]

        criteria = RoutingCriteria(task_type="rag_generation")

        try:
            # Use JSON mode if supported by the provider
            result = await self.client.chat(
                messages, criteria, response_format={"type": "json_object"}
            )

            # Extract JSON string (handling potential markdown blocks just in case)
            content = result.content.strip()
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()

            parsed = json.loads(content)

            return ProcessedQuery(
                original_query=query,
                expanded_queries=parsed.get("expanded_queries", []),
                metadata_filters=parsed.get("metadata_filters", {}),
                query_type=parsed.get("query_type", "factual"),
                hypothetical_document=parsed.get("hypothetical_document"),
            )
        except Exception:
            # Fallback on failure
            return ProcessedQuery(
                original_query=query,
                expanded_queries=[],
                metadata_filters={},
                query_type="factual",
                hypothetical_document=None,
            )

import threading
from typing import AsyncGenerator
from redis.asyncio import Redis
from opentelemetry import trace

from .base import BaseLLMProvider, ChatMessage, GenerationResult
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .router import ModelRouter, RoutingCriteria

tracer = trace.get_tracer(__name__)

class NeuroFlowClient:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, redis_client: Redis = None):
        with cls._lock:
            if cls._instance is None:
                if redis_client is None:
                    raise ValueError("redis_client must be provided on first instantiation")
                cls._instance = super(NeuroFlowClient, cls).__new__(cls)
                cls._instance._init(redis_client)
            return cls._instance

    def _init(self, redis_client: Redis):
        self.redis = redis_client
        self.router = ModelRouter(self.redis)
        self.providers: dict[str, BaseLLMProvider] = {}

    def _get_provider(self, provider_name: str, model_name: str) -> BaseLLMProvider:
        key = f"{provider_name}:{model_name}"
        if key not in self.providers:
            if provider_name == "openai":
                self.providers[key] = OpenAIProvider(model_name)
            elif provider_name == "anthropic":
                self.providers[key] = AnthropicProvider(model_name)
            else:
                raise ValueError(f"Unknown provider: {provider_name}")
        return self.providers[key]

    async def _record_metrics(self, result: GenerationResult):
        # Increment calls
        calls_key = f"metrics:model:{result.model}:calls"
        await self.redis.incr(calls_key)
        
        # Increment cost (Redis float increment)
        cost_key = f"metrics:model:{result.model}:cost_usd"
        await self.redis.incrbyfloat(cost_key, result.cost_usd)

    async def chat(self, messages: list[ChatMessage], criteria: RoutingCriteria, **kwargs) -> GenerationResult:
        chain = await self.router.route(criteria)
        
        last_exception = None
        for provider_name, model_name in chain:
            try:
                provider = self._get_provider(provider_name, model_name)
                
                with tracer.start_as_current_span("neuroflow.llm.chat") as span:
                    span.set_attribute("provider", provider_name)
                    span.set_attribute("model", model_name)
                    
                    result = await provider.complete(messages, **kwargs)
                    
                    # Decorate span with telemetry
                    span.set_attribute("input_tokens", result.input_tokens)
                    span.set_attribute("output_tokens", result.output_tokens)
                    span.set_attribute("cost_usd", result.cost_usd)
                    span.set_attribute("latency_ms", result.latency_ms)
                    
                    # Record metrics in Redis
                    await self._record_metrics(result)
                    
                    return result
            except Exception as e:
                # Catch non-retryable errors (or exhausted rate limit retries) and fallback
                last_exception = e
                continue
                
        raise RuntimeError(f"All fallback models failed for criteria {criteria}. Last error: {last_exception}") from last_exception

    async def stream_chat(self, messages: list[ChatMessage], criteria: RoutingCriteria, **kwargs) -> AsyncGenerator[str, None]:
        chain = await self.router.route(criteria)
        
        last_exception = None
        for provider_name, model_name in chain:
            try:
                provider = self._get_provider(provider_name, model_name)
                
                with tracer.start_as_current_span("neuroflow.llm.stream_chat") as span:
                    span.set_attribute("provider", provider_name)
                    span.set_attribute("model", model_name)
                    
                    # Test if stream initiates successfully
                    stream_gen = provider.stream(messages, **kwargs)
                    
                    # We can't easily fallback if the stream fails halfway through processing,
                    # but we can fallback if it fails to initiate.
                    # Since stream methods return generators or context managers, we must test initialization.
                    # Actually, if provider.stream itself raises, we catch it here.
                    
                    async def stream_wrapper():
                        async for chunk in stream_gen:
                            yield chunk
                            
                    return stream_wrapper()
            except Exception as e:
                last_exception = e
                continue
                
        raise RuntimeError(f"All fallback stream models failed for criteria {criteria}. Last error: {last_exception}") from last_exception

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Hardcode default to OpenAI text-embedding-3-small as requested in provider constraints
        provider = self._get_provider("openai", "text-embedding-3-small")
        
        with tracer.start_as_current_span("neuroflow.llm.embed") as span:
            span.set_attribute("provider", "openai")
            span.set_attribute("model", "text-embedding-3-small")
            
            embeddings = await provider.embed(texts)
            return embeddings

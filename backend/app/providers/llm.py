from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from backend.app.config import Settings

def text_terms(text: str) -> list[str]:
    lowered = text.lower()
    words = re.findall(r"[a-z0-9_]+", lowered)
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", lowered))
    words.extend(chinese[index : index + 2] for index in range(max(0, len(chinese) - 1)))
    words.extend(chinese)
    return words


def validate_embedding_vector(
    vector: list[float], expected_dimension: int, *, context: str
) -> list[float]:
    if not isinstance(vector, list):
        raise ValueError(f"EMBEDDING_INVALID_RESPONSE: {context} is not a vector")
    if len(vector) != expected_dimension:
        raise ValueError(
            f"EMBEDDING_DIMENSION_MISMATCH: {context} returned {len(vector)}, expected {expected_dimension}"
        )
    try:
        return [float(value) for value in vector]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"EMBEDDING_INVALID_RESPONSE: {context} contains non-numeric values") from exc


def validate_embedding_batch(
    vectors: list[list[float]], expected_dimension: int, *, expected_count: int | None = None
) -> list[list[float]]:
    if expected_count is not None and len(vectors) != expected_count:
        raise ValueError(
            f"EMBEDDING_ITEM_COUNT_MISMATCH: provider returned {len(vectors)}, expected {expected_count}"
        )
    return [
        validate_embedding_vector(vector, expected_dimension, context=f"embedding item {index}")
        for index, vector in enumerate(vectors)
    ]


class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        raise NotImplementedError

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    """Deterministic offline provider used by tests and the no-key demo."""

    def __init__(self, dimension: int = 1024) -> None:
        self.dimension = dimension

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        context = messages[-1]["content"] if messages else ""
        return "根据课程资料，可以得到以下结论：\n\n" + context[:1200]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimension
            for term in text_terms(text):
                digest = hashlib.sha256(term.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimension
                vector[index] += -1.0 if digest[4] & 1 else 1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, settings: Settings, fallback: LLMProvider | None = None) -> None:
        self.settings = settings
        self.fallback = fallback
        self.headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        # A provider instance is reused for the whole background job, so chat
        # and embedding calls share its connection pool instead of reconnecting
        # for every request in one RAG workflow.
        self._client: httpx.AsyncClient | None = None

    def _http_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient()
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        if not self.settings.llm_chat_model:
            if self.fallback is None:
                raise RuntimeError("chat model is not configured")
            return await self.fallback.chat(messages, **kwargs)
        timeout = float(kwargs.pop("_timeout", 30))
        response = await self._http_client().post(
            f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
            headers=self.headers,
            json={"model": self.settings.llm_chat_model, "messages": messages, **kwargs},
            timeout=httpx.Timeout(timeout),
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.settings.llm_embedding_model:
            if self.fallback is None:
                raise RuntimeError("embedding model is not configured")
            return await self.fallback.embed(texts)
        if not texts:
            return []
        batch_size = max(1, self.settings.llm_embedding_batch_size)
        embeddings: list[list[float]] = []
        client = self._http_client()
        for start in range(0, len(texts), batch_size):
            response = await client.post(
                f"{self.settings.llm_base_url.rstrip('/')}/embeddings",
                headers=self.headers,
                json={
                    "model": self.settings.llm_embedding_model,
                    "input": texts[start : start + batch_size],
                    "dimensions": self.settings.embedding_dimension,
                    "encoding_format": "float",
                },
                timeout=httpx.Timeout(30),
            )
            response.raise_for_status()
            batch = response.json().get("data")
            expected_count = min(batch_size, len(texts) - start)
            if not isinstance(batch, list) or len(batch) != expected_count:
                raise RuntimeError("embedding provider returned an unexpected item count")
            if all(isinstance(item, dict) and isinstance(item.get("index"), int) for item in batch):
                batch = sorted(batch, key=lambda item: item["index"])
                if [item["index"] for item in batch] != list(range(expected_count)):
                    raise RuntimeError("embedding provider returned invalid item indexes")
            try:
                vectors = [item["embedding"] for item in batch]
            except (KeyError, TypeError) as exc:
                raise RuntimeError("embedding provider returned an invalid payload") from exc
            embeddings.extend(
                validate_embedding_batch(
                    vectors,
                    self.settings.embedding_dimension,
                    expected_count=expected_count,
                )
            )
        return validate_embedding_batch(
            embeddings,
            self.settings.embedding_dimension,
            expected_count=len(texts),
        )


def llm_runtime_status(settings: Settings) -> dict[str, str | bool]:
    provider = settings.llm_provider.strip().lower()
    is_mock = provider == "mock"
    return {
        "provider": provider,
        "chat_model": settings.llm_chat_model if not is_mock else "",
        "chat_mode": "mock" if is_mock else "remote",
        "embedding_mode": "local" if is_mock or not settings.llm_embedding_model else "remote",
        "is_mock": is_mock,
    }


def get_llm_provider(settings: Settings) -> LLMProvider:
    fallback = MockLLMProvider(settings.embedding_dimension)
    provider = settings.llm_provider.strip().lower()
    if provider == "mock":
        return fallback
    if not provider:
        raise ValueError("LLM_PROVIDER must be configured explicitly")
    missing = [
        name
        for name, value in (
            ("LLM_BASE_URL", settings.llm_base_url),
            ("LLM_API_KEY", settings.llm_api_key),
            ("LLM_CHAT_MODEL", settings.llm_chat_model),
        )
        if not value.strip()
    ]
    if missing:
        raise ValueError(f"{provider} provider is missing required settings: {', '.join(missing)}")
    return OpenAICompatibleProvider(settings, fallback=fallback)

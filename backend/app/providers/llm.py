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
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.headers = {"Authorization": f"Bearer {settings.llm_api_key}"}

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
                headers=self.headers,
                json={"model": self.settings.llm_chat_model, "messages": messages, **kwargs},
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.settings.llm_base_url.rstrip('/')}/embeddings",
                headers=self.headers,
                json={"model": self.settings.llm_embedding_model, "input": texts},
            )
            response.raise_for_status()
            return [item["embedding"] for item in response.json()["data"]]


def get_llm_provider(settings: Settings) -> LLMProvider:
    if (
        settings.llm_provider != "mock"
        and settings.llm_base_url
        and settings.llm_api_key
        and settings.llm_embedding_model
    ):
        return OpenAICompatibleProvider(settings)
    return MockLLMProvider(settings.embedding_dimension)

from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.app.config import Settings
from backend.app.providers.llm import (
    MockLLMProvider,
    OpenAICompatibleProvider,
    get_llm_provider,
    llm_runtime_status,
)
from backend.app.services.rag import answer_from_sources


def test_chat_provider_can_use_local_embedding_fallback() -> None:
    settings = Settings(
        llm_provider="deepseek",
        llm_base_url="https://api.deepseek.com",
        llm_api_key="test-key",
        llm_chat_model="deepseek-chat",
        llm_embedding_model="",
        embedding_dimension=32,
    )

    provider = get_llm_provider(settings)

    assert isinstance(provider, OpenAICompatibleProvider)
    embeddings = asyncio.run(provider.embed(["local fallback embedding"]))
    assert len(embeddings) == 1
    assert len(embeddings[0]) == 32


def test_remote_embeddings_are_requested_in_ordered_batches(monkeypatch) -> None:
    requests: list[list[str]] = []

    class MockResponse:
        def __init__(self, texts: list[str]) -> None:
            self.texts = texts

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": [
                    {"embedding": [float(index)]}
                    for index, _text in enumerate(self.texts)
                ]
            }

    class MockClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, *, headers, json):
            del headers
            requests.append(json["input"])
            return MockResponse(json["input"])

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: MockClient())
    settings = Settings(
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_chat_model="qwen-chat",
        llm_embedding_model="qwen-embedding",
        llm_embedding_batch_size=2,
    )

    embeddings = asyncio.run(get_llm_provider(settings).embed(["a", "b", "c", "d", "e"]))

    assert requests == [["a", "b"], ["c", "d"], ["e"]]
    assert embeddings == [[0.0], [1.0], [0.0], [1.0], [0.0]]


def test_remote_provider_configuration_never_silently_falls_back_to_mock() -> None:
    settings = Settings(
        llm_provider="deepseek",
        llm_base_url="https://api.deepseek.com",
        llm_api_key="",
        llm_chat_model="deepseek-chat",
    )

    with pytest.raises(ValueError, match="LLM_API_KEY"):
        get_llm_provider(settings)


def test_mock_provider_and_runtime_status_are_explicit() -> None:
    settings = Settings(llm_provider="mock", llm_chat_model="ignored")

    assert isinstance(get_llm_provider(settings), MockLLMProvider)
    assert llm_runtime_status(settings) == {
        "provider": "mock",
        "chat_model": "",
        "chat_mode": "mock",
        "embedding_mode": "local",
        "is_mock": True,
    }


def test_remote_runtime_status_exposes_model_without_secret() -> None:
    settings = Settings(
        llm_provider="deepseek",
        llm_base_url="https://api.deepseek.com",
        llm_api_key="secret-key",
        llm_chat_model="deepseek-chat",
        llm_embedding_model="",
    )

    assert llm_runtime_status(settings) == {
        "provider": "deepseek",
        "chat_model": "deepseek-chat",
        "chat_mode": "remote",
        "embedding_mode": "local",
        "is_mock": False,
    }


def test_strict_rag_mode_calls_chat_provider_with_grounding_prompt() -> None:
    class RecordingProvider:
        messages: list[dict[str, str]] = []
        kwargs: dict = {}

        async def chat(self, messages, **kwargs):
            self.messages = messages
            self.kwargs = kwargs
            return "该协议使用 cobalt lanterns。[S1]"

        async def embed(self, _texts):
            return [[1.0]]

    provider = RecordingProvider()
    sources = [
        {
            "document_name": "protocol.txt",
            "page_number": 1,
            "quote": "The protocol uses cobalt lanterns.",
            "score": 0.9,
        }
    ]

    answer, sufficient = asyncio.run(
        answer_from_sources(provider, "What does the protocol use?", sources, "strict")
    )

    assert sufficient is True
    assert "cobalt lanterns" in answer
    assert provider.messages[0]["role"] == "system"
    assert "只能使用" in provider.messages[0]["content"]
    assert "[S1]" in provider.messages[1]["content"]
    assert provider.kwargs["temperature"] == 0.2
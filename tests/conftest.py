"""Shared test fixtures, including a mock OpenAI-compatible server.

A2/A4 gates need a provider that records exactly what it received, so the tests
can assert token budgets and image payloads instead of trusting logs.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import respx
from httpx import Response

from soapbot.providers.base import ProviderConfig
from soapbot.providers.openai_compat import OpenAICompatProvider
from soapbot.providers.router import ProviderRouter


class RecordedCall:
    def __init__(self, url: str, payload: dict[str, Any]) -> None:
        self.url = url
        self.payload = payload

    @property
    def messages(self) -> list[dict[str, Any]]:
        return self.payload.get("messages") or []

    def all_text(self) -> str:
        out: list[str] = []
        for m in self.messages:
            c = m.get("content")
            if isinstance(c, str):
                out.append(c)
            elif isinstance(c, list):
                for p in c:
                    if isinstance(p, dict) and p.get("type") == "text":
                        out.append(str(p.get("text", "")))
        return "\n".join(out)

    def image_parts(self) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = []
        for m in self.messages:
            c = m.get("content")
            if isinstance(c, list):
                for p in c:
                    if isinstance(p, dict) and p.get("type") == "image_url":
                        parts.append(p)
        return parts


class MockLLM:
    """Records requests and returns scripted replies."""

    def __init__(self) -> None:
        self.calls: list[RecordedCall] = []
        self.reply_queue: list[str] = []
        self.default_reply = "好的，我明白了。"
        self.router_mock: respx.MockRouter | None = None

    def push(self, reply: str) -> None:
        self.reply_queue.append(reply)

    def _next_reply(self, payload: dict[str, Any]) -> str:
        if self.reply_queue:
            return self.reply_queue.pop(0)
        return self.default_reply

    def handler(self, request) -> Response:
        payload = json.loads(request.content or b"{}")
        self.calls.append(RecordedCall(str(request.url), payload))
        reply = self._next_reply(payload)
        return Response(
            200,
            json={
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "model": payload.get("model", "mock-model"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": reply},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            },
        )

    def last_call(self) -> RecordedCall:
        if not self.calls:
            raise AssertionError("no LLM call recorded")
        return self.calls[-1]

    def reset(self) -> None:
        self.calls.clear()
        self.reply_queue.clear()


@pytest.fixture(autouse=True)
def _isolated_runtime(monkeypatch, tmp_path):
    """Keep every test off the real data directory and out of the bot runtime.

    Two separate hazards, both created by the app lifespan now doing real work:

    * ``data_dir`` defaults to the checkout's ``data/``. Without redirecting it, every
      TestClient would write a JWT key and a bootstrap token into the repository.
    * ``enable_runtime`` builds the pipeline, opens SQLite and dials whatever
      ``adapters.yaml`` names. Tests that only exercise HTTP routes should not pay
      that, and tests that *do* want it enable it explicitly — an opt-in is the only
      way the suite can tell "the runtime works" apart from "the runtime was skipped".
    """
    import os

    from soapbot.config import settings

    # The lifespan loads `.env` into ``os.environ`` on purpose, so adapters and providers
    # read the same variables the operator wrote. That also makes the process environment
    # a shared resource across tests: a developer with a real root `.env` (everyone who
    # has deployed from this checkout) would leak ``SOAPBOT_VOICE_ENABLED=false`` into
    # every later test, and a real environment variable outranks the temp ``.env`` a test
    # points ``Settings`` at. That is how the suite went green on CI and red on the
    # machine that actually deploys. Snapshot and restore, so each test starts from the
    # environment the runner gave it.
    saved_env = dict(os.environ)

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "enable_runtime", False)
    yield
    for key in set(os.environ) - set(saved_env):
        os.environ.pop(key, None)
    for key, value in saved_env.items():
        if os.environ.get(key) != value:
            os.environ[key] = value


@pytest.fixture
def mock_llm() -> MockLLM:
    return MockLLM()


@pytest.fixture
def mock_llm_router(mock_llm: MockLLM):
    with respx.mock(assert_all_called=False) as router:
        router.post(url__regex=r".*/chat/completions$").mock(side_effect=mock_llm.handler)
        router.post(url__regex=r".*/embeddings$").mock(
            return_value=Response(
                200,
                json={
                    "data": [
                        {"embedding": [0.1] * 8},
                        {"embedding": [0.2] * 8},
                    ]
                },
            )
        )
        yield router


@pytest.fixture
def provider_router() -> ProviderRouter:
    router = ProviderRouter(cooldown_seconds=1.0)
    router.add(
        OpenAICompatProvider(
            ProviderConfig(
                id="mock-openai",
                kind="openai_compat",
                base_url="https://mock.local/v1",
                api_key="test-key",
                model="mock-model",
                priority=1,
            )
        )
    )
    return router

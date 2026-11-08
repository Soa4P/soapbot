"""Shared test fixtures, including a mock OpenAI-compatible server.

A2/A4 gates need a provider that records exactly what it received, so the tests
can assert token budgets and image payloads instead of trusting logs.
"""

from __future__ import annotations

import contextlib
import faulthandler
import json
import os
from typing import Any

import pytest
import respx
from httpx import Response

from soapbot.config import settings
from soapbot.providers.base import ProviderConfig
from soapbot.providers.openai_compat import OpenAICompatProvider
from soapbot.providers.router import ProviderRouter

#: Per-test wall-clock ceiling before the suite dumps every thread's stack and exits.
#:
#: This exists because of a measured failure mode, not as general hygiene. A Windows
#: CI job sat on one test for ~69 minutes and was cancelled by the runner, which
#: reported `##[error]The operation was canceled.` and nothing else — no test name, no
#: traceback, no clue. Six consecutive pushes produced six identical red badges and
#: zero information, because a hang is invisible to pytest: it has no deadline, so it
#: waits forever and the *runner* decides when to stop, long after the useful moment.
#:
#: ``faulthandler.dump_traceback_later(..., exit=True)`` is the stdlib answer: it needs
#: no plugin, prints the stack of every thread to stderr, then hard-exits. A hang
#: therefore becomes a fast, self-explaining failure instead of a silent timeout.
#: Overridable so a slow machine can raise it, and disabled with 0.
#:
#: Deliberately *not* prefixed ``SOAPBOT_``: ``Settings`` rejects unknown ``SOAPBOT_``
#: variables outright, so a ``SOAPBOT_TEST_*`` knob would abort collection with a
#: validation error instead of configuring anything.
_HANG_LIMIT_SECONDS = float(os.environ.get("PYTEST_HANG_SECONDS", "180"))


#: Where the watchdog writes its dump.
#:
#: A file, not stderr, and that detail was measured rather than assumed. pytest
#: replaces fd 2 with a capture file for the whole session, so a dump written to stderr
#: — or to ``os.dup(2)`` taken after that swap — lands in a capture buffer that is
#: discarded when the process hard-exits. The first attempt at this watchdog fired
#: exactly on schedule and printed *nothing*, which is worse than no watchdog: it looks
#: like the hang was fixed. A dedicated file is outside pytest's capture machinery, so
#: the stack survives, and CI prints the file when the step fails.
_HANG_DUMP_PATH = os.environ.get("PYTEST_HANG_DUMP", "pytest-hang-dump.log")
_DUMP_STREAM = None
if _HANG_LIMIT_SECONDS > 0:
    with contextlib.suppress(OSError, ValueError):
        _DUMP_STREAM = open(_HANG_DUMP_PATH, "a", encoding="utf-8", buffering=1)  # noqa: SIM115


@pytest.fixture(autouse=True)
def _no_test_may_hang():
    """Arm a hard deadline around every test, so a hang reports itself.

    Deliberately ``exit=True``: the point is to stop the run at the hang, not to let
    it continue for another hour and hide which test did it.
    """
    if _HANG_LIMIT_SECONDS > 0:
        faulthandler.dump_traceback_later(
            _HANG_LIMIT_SECONDS, exit=True, file=_DUMP_STREAM
        )
    try:
        yield
    finally:
        if _HANG_LIMIT_SECONDS > 0:
            faulthandler.cancel_dump_traceback_later()


@pytest.fixture(autouse=True)
def _business_tests_are_not_login_scripts(monkeypatch):
    """Keep the ~200 HTTP assertions in this suite about the feature under test.

    Production defaults to ``strict_loopback_auth=True``: a loopback client may read
    but needs a credential to change state. Several hundred existing assertions send
    unauthenticated POSTs from TestClient to exercise config merging, plugin loading,
    memory scopes and so on. Rewriting each one to log in first would test the login
    helper far more often than it tests the thing the file is named after.

    The strict boundary itself is not exempted from testing — tests/test_auth_cookie.py
    turns the setting back on explicitly and pins login, CSRF, role floors and the
    loopback read/write split. ``strict_startup`` is off here for the same reason:
    many fixtures deliberately install a broken or absent adapter to test the panel.
    """
    monkeypatch.setattr(settings, "strict_loopback_auth", False)
    monkeypatch.setattr(settings, "strict_startup", False)


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
        if payload.get("stream"):
            return self._sse(reply, payload)
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

    def _sse(self, reply: str, payload: dict[str, Any]) -> Response:
        """Answer a ``stream: true`` request the way an OpenAI-compatible server does.

        This mock used to return a plain JSON body no matter what was asked. The
        streaming parser looked for ``data:`` lines, found none, yielded nothing, and
        the router fell back to a second, non-streaming call — which consumed a
        *second* scripted reply. So a test that pushed one reply then asserted on the
        answer got ``default_reply`` instead, and a test asserting ``calls == 1`` saw
        two.

        Both symptoms were invisible on a machine whose root ``.env`` sets
        ``SOAPBOT_STREAM_REPLY=false``: with streaming off, the mock was never asked
        for SSE and the suite was green. CI has no ``.env``, so the default (streaming
        on) applied and three tests failed there. Worse than the failure: every
        streaming test was silently exercising the fallback path.
        """
        model = payload.get("model", "mock-model")
        # Several small deltas rather than one, so the sentence assembler has something
        # to assemble — a single delta would make "progressive" untestable.
        chunks = [reply[i : i + 4] for i in range(0, len(reply), 4)] or [""]

        def frame(delta: dict[str, Any], finish: str | None) -> str:
            return "data: " + json.dumps(
                {
                    "id": "chatcmpl-mock",
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
                },
                ensure_ascii=False,
            )

        lines = [frame({"content": piece}, None) for piece in chunks]
        lines.append(frame({}, "stop"))
        lines.append("data: [DONE]")
        body = ("\n\n".join(lines) + "\n\n").encode("utf-8")
        return Response(200, content=body, headers={"content-type": "text/event-stream"})

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


@pytest.fixture(autouse=True)
def _reset_audit_log():
    """The audit log is a process-wide singleton; one test's events must not reach the next.

    `test_security_e2e.py::test_injection_refused_before_model` asserts on
    `recent(kind="injection")[-1]` — a positional claim about a shared deque. Without
    this reset the assertion depends on no earlier test having logged an injection
    event: it passes alone, passes as a file, and fails in a full run. That is the
    hardest kind of failure to attribute, and it was reproduced exactly that way before
    this fixture existed.
    """
    from soapbot.security.audit import get_audit_log

    log = get_audit_log()
    log.clear()
    yield
    log.clear()


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

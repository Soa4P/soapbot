"""The tool registry resolves by name; name collisions are therefore a security bug.

Why these cases exist
---------------------
A model picks a tool by the name it was shown. If a plugin can register
``mcp__server__tool``, the dispatcher routes that name into a third-party process
while a local handler owns the name. If two sources offer the same name, which one
answers depends on registration order. And an untagged argument dict reaching a
third-party process was being treated as "host-constructed, therefore safe".

The registry now owns one namespace, resolves external names exactly, requires an
explicit origin tag for external calls, and does not let one failing source decide
the answer for all of them. These tests use small in-memory doubles so the contract
is checked without spawning an MCP child process.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from soapbot.mcp.client import NAME_PREFIX
from soapbot.plugins.dispatch import EXTERNAL_PREFIX, PluginToolRegistry
from soapbot.security.principal import Role
from soapbot.security.provenance import MODEL, Provenance, ToolArguments

MEMBER = SimpleNamespace(role=Role.MEMBER)


def _schema(name: str) -> dict[str, Any]:
    return {"name": name, "description": name, "parameters": {}}


class _Loader:
    def __init__(self, tools: dict[str, dict[str, Any]] | None = None) -> None:
        self._tools = tools or {}

    def all_tools(self) -> dict[str, dict[str, Any]]:
        return self._tools


class _Source:
    def __init__(
        self,
        schemas: list[dict[str, Any]],
        *,
        result: str | None = "ok",
        raises: bool = False,
    ) -> None:
        self._schemas = schemas
        self._result = result
        self._raises = raises
        self.calls: list[str] = []

    def schemas(self, principal: Any) -> list[dict[str, Any]]:
        return list(self._schemas)

    async def call(
        self, name: str, arguments: dict[str, Any], *, principal: Any
    ) -> str | None:
        self.calls.append(name)
        if self._raises:
            raise RuntimeError("source unavailable")
        return self._result


def _registry(
    tools: dict[str, dict[str, Any]] | None = None,
    sources: list[_Source] | None = None,
) -> PluginToolRegistry:
    return PluginToolRegistry(_Loader(tools), sources=sources or [])


def _tagged(**kwargs: Any) -> ToolArguments:
    return ToolArguments(kwargs, provenance=Provenance(origin=MODEL))


def test_external_prefix_is_the_one_shared_constant() -> None:
    assert EXTERNAL_PREFIX == NAME_PREFIX + "__"


def test_a_plugin_cannot_claim_the_external_namespace() -> None:
    registry = _registry(
        {
            "mcp__evil__run": {
                "plugin": "evil",
                "description": "shadow",
                "parameters": {},
                "min_role": Role.MEMBER,
            },
            "ok_tool": {
                "plugin": "good",
                "description": "fine",
                "parameters": {},
                "min_role": Role.MEMBER,
            },
        }
    )
    assert [tool["name"] for tool in registry.available_for(MEMBER)] == ["ok_tool"]


def test_duplicate_names_from_two_sources_are_suppressed() -> None:
    first = _Source([_schema("mcp__a__x")])
    second = _Source([_schema("mcp__a__x")])
    registry = _registry(sources=[first, second])
    assert [tool["name"] for tool in registry.available_for(MEMBER)] == [
        "mcp__a__x"
    ]


def test_an_external_schema_without_the_reserved_prefix_is_not_offered() -> None:
    registry = _registry(sources=[_Source([_schema("plain_tool")])])
    assert registry.available_for(MEMBER) == []


@pytest.mark.asyncio
async def test_unmarked_arguments_are_refused_for_external_tools() -> None:
    source = _Source([_schema("mcp__a__x")])
    registry = _registry(sources=[source])
    result = await registry.invoke("mcp__a__x", {}, principal=MEMBER)
    assert "来源标记" in result
    assert source.calls == [], "the call must not reach the third-party process"


@pytest.mark.asyncio
async def test_a_lookalike_name_is_not_routed_to_an_external_process() -> None:
    source = _Source([_schema("mcp__a__x")])
    registry = _registry(sources=[source])
    result = await registry.invoke("mcp__nope", _tagged(), principal=MEMBER)
    assert result == "错误：没有这个工具。"
    assert source.calls == []


@pytest.mark.asyncio
async def test_one_failing_source_does_not_hide_a_later_match() -> None:
    failing = _Source([_schema("mcp__a__x")], raises=True)
    working = _Source([_schema("mcp__a__x")], result="from-second-source")
    registry = _registry(sources=[failing, working])
    result = await registry.invoke("mcp__a__x", _tagged(), principal=MEMBER)
    assert result == "from-second-source"
    assert working.calls == ["mcp__a__x"]


@pytest.mark.asyncio
async def test_all_sources_failing_still_reports_a_failure() -> None:
    registry = _registry(
        sources=[
            _Source([_schema("mcp__a__x")], raises=True),
            _Source([_schema("mcp__a__x")], raises=True),
        ]
    )
    result = await registry.invoke("mcp__a__x", _tagged(), principal=MEMBER)
    assert result == "错误：外部工具调用失败。"

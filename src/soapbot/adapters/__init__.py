"""Adapter registry.

The core resolves adapters by name here so a broken adapter never breaks import
of the package. Concrete adapters are imported lazily on first use.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from soapbot.core.adapter import Adapter

_FACTORIES: dict[str, Callable[..., Adapter]] = {}


def register(name: str, factory: Callable[..., Adapter]) -> None:
    _FACTORIES[name] = factory


def available() -> list[str]:
    return ["onebot11", "qq_official"]


def create(kind: str, **kwargs: Any) -> Adapter:
    if kind == "onebot11":
        from soapbot.adapters.onebot11 import OneBot11Adapter

        return OneBot11Adapter(**kwargs)
    if kind == "qq_official":
        from soapbot.adapters.qq_official import QQOfficialAdapter

        return QQOfficialAdapter(**kwargs)
    if kind in _FACTORIES:
        return _FACTORIES[kind](**kwargs)
    raise ValueError(f"unknown adapter: {kind}")


__all__ = ["available", "create", "register"]

"""Provider and adapter configuration loaded from YAML files.

Why files rather than the database
----------------------------------
These describe *how the process connects to the outside world* — which endpoints to
dial, which tokens to present. A bot that cannot dial its protocol endpoint cannot
receive the very messages that would let anyone configure it, so this layer has to be
readable by an operator with a text editor and no running service. Provider API keys
that change at runtime still live in the encrypted database; this file is for
bootstrap wiring.

Failure policy, stated explicitly because the wrong choice here is invisible
--------------------------------------------------------------------------
* **File absent** → empty list, one log line. A fresh install has no adapters
  configured and must still boot: ``soapbot start`` with no config should give a
  reachable management API, not a crash loop.
* **File present but malformed** → raise. A typo that silently yields zero providers
  produces the worst possible symptom: the service is up, the health check is green,
  and every message gets no reply. Failing loudly at startup is the only diagnostic
  that reaches the operator before users do.
* **Secret reference unresolvable** → raise, for the same reason. Sending an empty
  API key turns a configuration mistake into a stream of 401s attributed to the
  upstream provider.

Secret forms accepted anywhere a secret is expected::

    api_key: sk-literal-value        # literal (fine for local experiments)
    api_key: env:DEEPSEEK_API_KEY    # read from the environment
    api_key: enc:v1:gAAAAA...        # Fernet ciphertext, via soapbot.security.crypto
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from soapbot.providers.base import ProviderConfig
from soapbot.providers.router import ProviderRouter, build_provider

logger = logging.getLogger(__name__)

ENV_PREFIX = "env:"
"""Explicit indirection marker. A bare ``DEEPSEEK_API_KEY`` is *not* treated as a
variable name: an operator who pastes a key that happens to look like an identifier
would otherwise get a confusing "variable not set" instead of an auth failure."""

#: Keys whose value is treated as a secret and therefore supports the forms above.
#: Detected by name so the operator does not have to remember a separate syntax for
#: each adapter — and so a new adapter's ``app_secret`` is covered without a code
#: change.
SECRET_KEYS = frozenset(
    {"api_key", "access_token", "app_secret", "token", "secret", "password", "webhook_secret"}
)


class ConfigError(RuntimeError):
    """Raised when a configuration file exists but cannot be honoured."""


@dataclass(slots=True)
class AdapterConfig:
    """One adapter entry: a registry ``kind`` plus its constructor options."""

    kind: str
    options: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


def env_file_hint() -> str:
    """Where to write the missing variable — named, because "set it in the environment"
    sends someone to edit their shell when every other value lives in ``.env``."""
    path = os.environ.get("SOAPBOT_ENV_FILE", "")
    return path or ".env"


def resolve_secret(value: Any, *, field_name: str = "value") -> str:
    """Resolve ``env:`` / ``enc:v1:`` indirection; return literals unchanged."""
    if value is None:
        return ""
    text = str(value)
    if text.startswith(ENV_PREFIX):
        var = text[len(ENV_PREFIX) :].strip()
        if not var:
            raise ConfigError(f"{field_name} uses 'env:' without a variable name")
        resolved = os.environ.get(var, "")
        if not resolved:
            # Not "fall back to empty": an empty credential is accepted by the
            # transport and rejected by the upstream, which turns a missing
            # environment variable into a runtime auth failure nobody can trace back
            # to this file.
            # The strictness stays — an empty key becomes a 401 upstream — but refusing to
            # boot without saying how to make it true is just a bad error message wearing a
            # principle as a costume.
            raise ConfigError(
                f"{field_name} references unset environment variable {var!r}. "
                f"Set {var} in {env_file_hint()}, or change the entry to a literal key "
                "(Provider 列表在第 07 页)。"
            )
        return resolved
    if text.startswith("enc:v1:"):
        from soapbot.security.crypto import get_secret_box

        try:
            return get_secret_box().decrypt(text)
        except Exception as exc:
            raise ConfigError(f"{field_name} could not be decrypted: {exc}") from exc
    return text


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        logger.info("no config file at %s; treating as empty", path)
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return raw


def parse_providers(data: dict[str, Any], source: str = "<memory>") -> list[ProviderConfig]:
    """Turn an already-parsed mapping into :class:`ProviderConfig` objects.

    Split out of :func:`load_providers` so the write path can validate a *candidate*
    document with the exact same rules that run at startup. Re-implementing the checks
    for the editor is how a panel ends up able to save a file the service then refuses
    to boot from — the one failure mode a config UI must never have.
    """
    entries = data.get("providers") or []
    if not isinstance(entries, list):
        raise ConfigError(f"{source}: 'providers' must be a list")

    out: list[ProviderConfig] = []
    seen: set[str] = set()
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            raise ConfigError(f"{source}: providers[{index}] must be a mapping")
        pid = str(item.get("id") or "").strip()
        kind = str(item.get("kind") or "").strip()
        if not pid or not kind:
            # A provider without an id cannot be addressed for failover or reported
            # in the UI; without a kind it cannot be constructed. Both are authoring
            # errors, not defaults.
            raise ConfigError(f"{source}: providers[{index}] requires 'id' and 'kind'")
        if pid in seen:
            raise ConfigError(f"{source}: duplicate provider id {pid!r}")
        seen.add(pid)

        out.append(
            ProviderConfig(
                id=pid,
                kind=kind,
                label=str(item.get("label") or ""),
                base_url=str(item.get("base_url") or ""),
                api_key=resolve_secret(item.get("api_key"), field_name=f"providers[{pid}].api_key"),
                model=str(item.get("model") or ""),
                embed_model=str(item.get("embed_model") or ""),
                vision_model=str(item.get("vision_model") or ""),
                timeout=float(item.get("timeout", 60.0)),
                max_retries=int(item.get("max_retries", 2)),
                priority=int(item.get("priority", 100)),
                enabled=bool(item.get("enabled", True)),
                extra=dict(item.get("extra") or {}),
            )
        )
    return out


def load_providers(path: Path | None) -> list[ProviderConfig]:
    """Read ``providers:`` entries into :class:`ProviderConfig` objects."""
    if path is None:
        return []
    return parse_providers(_read_yaml(path), source=str(path))


def load_adapters(path: Path | None) -> list[AdapterConfig]:
    """Read ``adapters:`` entries, resolving secret-valued options."""
    if path is None:
        return []
    data = _read_yaml(path)
    entries = data.get("adapters") or []
    if not isinstance(entries, list):
        raise ConfigError(f"{path}: 'adapters' must be a list")

    out: list[AdapterConfig] = []
    names: set[str] = set()
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            raise ConfigError(f"{path}: adapters[{index}] must be a mapping")
        kind = str(item.get("kind") or "").strip()
        if not kind:
            raise ConfigError(f"{path}: adapters[{index}] requires 'kind'")
        if kind in names:
            # The runtime keys adapters by ``meta.name``, which is the kind, so a
            # second entry would silently replace the first — including its
            # connection settings. Two accounts need two adapter kinds or a
            # registry registration, not a duplicate key.
            raise ConfigError(f"{path}: duplicate adapter kind {kind!r}")
        names.add(kind)

        options: dict[str, Any] = {}
        for key, value in item.items():
            if key in ("kind", "enabled"):
                continue
            options[key] = (
                resolve_secret(value, field_name=f"adapters[{kind}].{key}")
                if key in SECRET_KEYS
                else value
            )
        out.append(
            AdapterConfig(kind=kind, options=options, enabled=bool(item.get("enabled", True)))
        )
    return out


def build_router(configs: list[ProviderConfig]) -> ProviderRouter:
    """Construct a router holding every configured provider.

    A provider whose ``kind`` is unknown aborts startup rather than being skipped:
    skipping means the configured failover chain silently loses a link, and the
    operator's only clue is a bot that behaves worse than its config says it should.
    """
    router = ProviderRouter()
    for config in configs:
        try:
            router.add(build_provider(config))
        except Exception as exc:
            raise ConfigError(f"provider {config.id!r} (kind={config.kind}) failed: {exc}") from exc
    return router

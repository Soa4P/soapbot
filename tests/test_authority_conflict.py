"""One QQ number, one role.

Permission resolution takes the highest rank, so a number listed as both owner and
member behaves as owner. The lists then read as "this person is a member", removing
them from the member list appears to do nothing, and the file contradicts itself. The
write is refused instead.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from fastapi import HTTPException

from soapbot.api import security as security_api
from soapbot.security.principal import Role


def _auth(role: Role = Role.OWNER) -> dict[str, Any]:
    return {"mode": "token", "role": role.value, "subject": "operator"}


class _Request:
    """Enough of a Starlette request for the error path."""

    client: ClassVar[None] = None
    headers: ClassVar[dict[str, str]] = {}


def _patch(**kwargs: list[str]) -> Any:
    return security_api.AuthorityPatch(**kwargs)


@pytest.mark.asyncio
async def test_the_same_qq_in_two_roles_is_refused(monkeypatch) -> None:
    written: list[str] = []
    monkeypatch.setattr(
        "soapbot.core.config_write.write_atomic", lambda *_a, **_k: written.append("x")
    )

    with pytest.raises(HTTPException) as exc:
        await security_api.write_authority(
            _patch(owners=["111"], admins=["111"], members=[]),
            _Request(),  # type: ignore[arg-type]
            _auth(),
        )

    assert exc.value.status_code == 400
    assert "111" in exc.value.detail
    assert "owner" in exc.value.detail and "admin" in exc.value.detail
    assert written == [], "nothing may be written when the lists contradict each other"


@pytest.mark.asyncio
async def test_three_way_conflict_names_every_role(monkeypatch) -> None:
    monkeypatch.setattr("soapbot.core.config_write.write_atomic", lambda *_a, **_k: None)

    with pytest.raises(HTTPException) as exc:
        await security_api.write_authority(
            _patch(owners=["111"], admins=["111"], members=["111"]),
            _Request(),  # type: ignore[arg-type]
            _auth(),
        )

    detail = exc.value.detail
    for role in ("owner", "admin", "member"):
        assert role in detail


@pytest.mark.asyncio
async def test_the_inherited_owner_is_not_reported_as_a_conflict(monkeypatch, tmp_path) -> None:
    """The first-run owner is re-inserted, so it must be reconciled *before* the check.

    It used to be inserted after the conflict check, which meant an operator who listed
    that same account as an admin got a 400 naming a conflict they could not fix — the
    account is not in their payload, so removing it from the form is impossible. Owner
    outranks admin, so the stale lower entry is dropped silently instead.
    """
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    monkeypatch.setattr("soapbot.api.settings._env_path", lambda: env)
    monkeypatch.setattr("soapbot.core.config_write.write_atomic", lambda *_a, **_k: None)
    # `settings` is imported inside the handler, so the patch has to land on the module
    # object itself rather than on an attribute of `security_api`.
    from soapbot.config import settings as live_settings

    monkeypatch.setattr(live_settings, "first_run_owner", "999")

    body = await security_api.write_authority(
        _patch(owners=["111"], admins=["999"], members=[]),
        _Request(),  # type: ignore[arg-type]
        _auth(),
    )

    assert "999" in body["owners"]
    assert "999" not in body["admins"], "owner outranks admin; the lower entry is dropped"


@pytest.mark.asyncio
async def test_disjoint_lists_are_accepted(monkeypatch, tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("SOAPBOT_OWNER_IDS=\n", encoding="utf-8")
    monkeypatch.setattr("soapbot.api.settings._env_path", lambda: env)
    monkeypatch.setattr("soapbot.core.config_write.write_atomic", lambda *_a, **_k: None)

    body = await security_api.write_authority(
        _patch(owners=["111"], admins=["222"], members=["333"]),
        _Request(),  # type: ignore[arg-type]
        _auth(),
    )

    assert body["ok"] is True
    assert body["owners"] == ["111"]

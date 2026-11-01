"""A signed token must be revocable.

Before this, ``TokenService.verify`` had no revocation input at all: a token was valid for
its full ``ttl`` (72 hours by default) no matter what the operator did. Rotating the
signing secret was the only remedy, and it logged out every session at once — so the
practical answer to "my token leaked" was "wait three days".

Two mechanisms are tested separately because they answer different questions: a per-token
``jti`` revocation (logout) and a global cut-off (the key may be compromised, and the
operator does not know which ids exist).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from soapbot.security.revocation import RevocationStore
from soapbot.security.tokens import TokenError, TokenService

SECRET = "unit-test-secret-that-is-long-enough-to-pass-the-check"


def _store(tmp_path: Path) -> RevocationStore:
    return RevocationStore(tmp_path / "revocations.json")


def _service(tmp_path: Path, store: RevocationStore | None = None) -> TokenService:
    return TokenService(
        secret=SECRET,
        ttl_hours=1,
        secret_file=tmp_path / "jwt.key",
        revocations=store,
    )


# ------------------------------------------------------------------ store basics
def test_a_revoked_id_is_revoked(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert not store.is_revoked("abc", issued_at=int(time.time()))
    assert store.revoke("abc", exp=int(time.time()) + 3600) is True
    assert store.is_revoked("abc", issued_at=int(time.time()))


def test_revoking_twice_is_idempotent(tmp_path: Path) -> None:
    """A double logout must not corrupt the file or claim a second revocation."""
    store = _store(tmp_path)
    exp = int(time.time()) + 3600
    assert store.revoke("abc", exp=exp) is True
    assert store.revoke("abc", exp=exp) is False
    assert store.snapshot()["count"] == 1


def test_revocation_survives_a_restart(tmp_path: Path) -> None:
    """The point of persisting it: a restart must not un-revoke anything."""
    Path(tmp_path, "revocations.json")
    first = _store(tmp_path)
    first.revoke("abc", exp=int(time.time()) + 3600)

    second = _store(tmp_path)  # fresh object, reads the file
    assert second.is_revoked("abc", issued_at=int(time.time()))


def test_prune_drops_entries_for_expired_tokens(tmp_path: Path) -> None:
    """An id whose token has expired needs no entry: the signature check rejects it."""
    store = _store(tmp_path)
    now = int(time.time())
    store.revoke("old", exp=now - 10)
    store.revoke("live", exp=now + 3600)

    assert store.prune(now=now) == 1
    assert not store.is_revoked("old", issued_at=now)
    assert store.is_revoked("live", issued_at=now)


def test_a_corrupt_file_refuses_to_load(tmp_path: Path) -> None:
    """Fail closed. Treating an unreadable file as empty would un-revoke everything."""
    path = tmp_path / "revocations.json"
    path.write_text("{ not json", encoding="utf-8")
    store = RevocationStore(path)
    with pytest.raises(RuntimeError, match="unreadable"):
        store.load()


def test_the_file_is_not_world_readable_on_posix(tmp_path: Path) -> None:
    if not hasattr(__import__("os"), "geteuid"):
        pytest.skip("POSIX-only property")
    store = _store(tmp_path)
    store.revoke("abc", exp=int(time.time()) + 60)
    mode = (tmp_path / "revocations.json").stat().st_mode & 0o077
    assert mode == 0, oct(mode)


# --------------------------------------------------------------- verify() wiring
def test_verify_rejects_a_revoked_token(tmp_path: Path) -> None:
    store = _store(tmp_path)
    service = _service(tmp_path, store)

    token, claims = service.issue("operator")
    assert service.verify(token).subject == "operator"  # sanity: it works first

    store.revoke(claims.token_id, exp=claims.expires_at)

    with pytest.raises(TokenError, match="revoked"):
        service.verify(token)


def test_verify_is_unaffected_when_no_store_is_configured(tmp_path: Path) -> None:
    """``None`` must keep the old behaviour: tests and embedded callers rely on it."""
    service = _service(tmp_path, None)
    token, _claims = service.issue("operator")
    assert service.verify(token).subject == "operator"


def test_revoke_all_invalidates_tokens_the_operator_never_enumerated(tmp_path: Path) -> None:
    """The stolen-laptop case: no jti known, every older token must still die.

    Time is supplied explicitly rather than slept through: the cut-off is whole seconds,
    so a token issued and a revoke-all performed inside the same second is genuinely
    indistinguishable by timestamp alone (which is why the endpoint also revokes the
    caller's own id). Sleeping a second per test to dodge that would make the suite slow
    and the assertion no more meaningful.
    """
    store = _store(tmp_path)
    service = _service(tmp_path, store)

    old_token, claims = service.issue("operator")
    store.revoke_all(now=claims.issued_at + 1)

    with pytest.raises(TokenError, match="revoked"):
        service.verify(old_token)


def test_a_token_newer_than_the_cut_off_still_works(tmp_path: Path) -> None:
    """Otherwise "revoke everything" also breaks the recovery login."""
    store = _store(tmp_path)
    service = _service(tmp_path, store)

    store.revoke_all(now=int(time.time()) - 10)
    fresh_token, _ = service.issue("operator")

    assert service.verify(fresh_token).subject == "operator"


def test_the_caller_own_token_dies_even_within_the_same_second(tmp_path: Path) -> None:
    """Why the endpoint revokes by id *and* by cut-off.

    A timestamp comparison cannot tell "issued one millisecond before the revoke" from
    "issued one millisecond after" once both are truncated to seconds. Revoking the
    caller's ``jti`` removes the ambiguity for the one token that matters most.
    """
    store = _store(tmp_path)
    service = _service(tmp_path, store)

    token, claims = service.issue("operator")
    store.revoke(claims.token_id, claims.expires_at)  # what the endpoint does first
    store.revoke_all(now=claims.issued_at)  # and then the cut-off

    with pytest.raises(TokenError, match="revoked"):
        service.verify(token)


def test_a_token_issued_at_the_cut_off_is_not_revoked(tmp_path: Path) -> None:
    """The boundary exists so "revoke all" cannot log the operator out permanently.

    With ``<=`` the replacement token issued in the same second is itself revoked, and
    the bootstrap token needed to log back in was consumed at first login — the operator
    ends up locked out of their own panel. The one-second window this opens is not
    exploitable by anyone who cannot already mint tokens, and such an attacker controls
    ``iat`` anyway.
    """
    store = _store(tmp_path)
    now = int(time.time())
    store.revoke_all(now=now)

    assert store.is_revoked("", issued_at=now - 10), "an older token must die"
    assert not store.is_revoked("", issued_at=now), "the replacement token must survive"


# ------------------------------------------------------------------- endpoints
def test_the_endpoints_are_registered() -> None:
    """Cheap wiring check: a route nobody mounted is a feature nobody has."""
    from soapbot.api.auth import router

    paths = {(route.path, tuple(sorted(route.methods or ()))) for route in router.routes}
    assert ("/api/auth/logout", ("POST",)) in paths
    assert ("/api/auth/revoke-all", ("POST",)) in paths
    assert ("/api/auth/revocations", ("GET",)) in paths


def test_snapshot_exposes_no_token_material(tmp_path: Path) -> None:
    """The panel endpoint must not become a way to harvest ids for a targeted attack."""
    store = _store(tmp_path)
    store.revoke("secret-jti-value", exp=int(time.time()) + 60)
    payload = store.snapshot()

    assert payload["count"] == 1
    assert set(payload) == {"revoked_before", "count", "tokens"}
    assert set(payload["tokens"][0]) == {"jti", "expires_at", "expired"}
    # The jti is an opaque id, not the token; but bound its exposure anyway.
    assert json.dumps(payload).count("secret-jti-value") == 1

"""An idle window on admin tokens, off by default.

The point of the option is narrow: a token that was signed correctly and has not
expired can still be a credential nobody is watching. Operators who want dormancy to
end the session can set ``SOAPBOT_JWT_IDLE_HOURS``; everyone else keeps the old
behaviour exactly, which is why the default is ``0`` and why the first case below is a
regression test rather than an afterthought.

``verify(now=...)`` exists so these cases need no sleeping and no monkeypatching of the
process clock. Only the idle comparison uses the injected value; expiry is still
PyJWT's job against real time, which is what the "still inside ttl" comment marks.
"""

from __future__ import annotations

import time

import pytest

from soapbot.security.tokens import TokenError, TokenService

SECRET = "idle-decay-test-signing-key-32-bytes-min"


def _service(**kwargs) -> TokenService:
    return TokenService(secret=SECRET, **kwargs)


def test_idle_window_is_off_by_default() -> None:
    service = _service()
    token, _ = service.issue("operator")
    # Two days later, but still inside the 72 h ttl: an unset option must not change
    # what a signed token means.
    claims = service.verify(token, now=time.time() + 2 * 24 * 3600)
    assert claims.subject == "operator"


def test_a_token_unused_past_the_window_is_refused() -> None:
    service = _service(idle_hours=1)
    token, claims = service.issue("operator")

    with pytest.raises(TokenError) as raised:
        service.verify(token, now=time.time() + 2 * 3600)
    assert "idle" in str(raised.value)

    # It stays dead: the next request arriving later must not revive it.
    with pytest.raises(TokenError):
        service.verify(token, now=time.time() + 3 * 3600)
    assert claims.token_id


def test_activity_slides_the_window() -> None:
    service = _service(idle_hours=1)
    token, _ = service.issue("operator")
    start = time.time()

    # Every half hour for five hours: each use is inside the window, so the token lives
    # well past the point where a single 1 h gap would have killed it.
    for step in range(1, 11):
        service.verify(token, now=start + step * 1800)

    with pytest.raises(TokenError):
        service.verify(token, now=start + 10 * 1800 + 2 * 3600)


def test_refresh_starts_a_new_window() -> None:
    service = _service(idle_hours=1)
    first, _ = service.issue("operator")
    now = time.time()
    service.verify(first, now=now)

    second, second_claims = service.issue("operator")
    # A fresh jti is a fresh credential, usable immediately even though the old one is
    # about to go stale.
    verified = service.verify(second, now=now)
    assert verified.token_id == second_claims.token_id

    # Two hours of silence still kills the original token.
    with pytest.raises(TokenError):
        service.verify(first, now=now + 2 * 3600)


def test_the_bookkeeping_map_is_bounded() -> None:
    service = _service(idle_hours=1)
    for _ in range(1500):
        service.issue("operator")
    assert len(service._last_used) <= service._idle_capacity


def test_revocation_is_reported_before_idleness() -> None:
    class _AllRevoked:
        def is_revoked(self, jti: str, issued_at: float) -> bool:
            return True

    service = _service(idle_hours=1, revocations=_AllRevoked())
    token, _ = service.issue("operator")

    with pytest.raises(TokenError) as raised:
        service.verify(token, now=time.time() + 5 * 3600)
    # A caller must not learn whether a token was once ours and went idle; "revoked"
    # is the coarse answer that was already there.
    assert "revoked" in str(raised.value)

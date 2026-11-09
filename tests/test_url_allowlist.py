"""A destination pre-allow-list, checked before the private-address deny-list.

Why this exists
---------------
``assert_url_allowed`` used to be a pure deny-list: reject loopback, link-local,
RFC1918, blocked ports, credentials-in-URL, and let everything else through. That is
the right answer to "is this address obviously bad?" but the wrong answer to "may we
talk to this host at all?" — any public hostname passes, including one the operator
never agreed to and one the model produced from untrusted text.

The list is checked *first*, and the deny-list still runs afterwards. An allow-list
entry can be stale or mistyped, and defence in depth should not be traded away just
because a stricter check was added.
"""

from __future__ import annotations

import pytest

from soapbot.plugins import sandbox
from soapbot.plugins.sandbox import SafeHttpClient, SSRFBlockedError, assert_url_allowed


def test_a_public_host_not_on_the_list_is_rejected() -> None:
    """The whole point: a perfectly ordinary public host is not implicitly allowed."""
    with pytest.raises(SSRFBlockedError, match="not in the destination allow-list"):
        assert_url_allowed(
            "https://api.example.com/v1", allowed_hosts=frozenset({"other.example"})
        )


def test_exact_matches_and_subdomain_rules() -> None:
    allowed = ("Example.COM.", ".trusted.example")
    assert_url_allowed("https://example.com/x", allowed_hosts=allowed)
    assert_url_allowed("https://EXAMPLE.com/x", allowed_hosts=allowed)
    assert_url_allowed("https://trusted.example/x", allowed_hosts=allowed)
    assert_url_allowed("https://a.b.trusted.example/x", allowed_hosts=allowed)

    # A suffix that merely looks like the rule must not match.
    with pytest.raises(SSRFBlockedError):
        assert_url_allowed("https://nottrusted.example/x", allowed_hosts=allowed)


def test_an_empty_allow_list_is_fail_closed() -> None:
    with pytest.raises(SSRFBlockedError, match="not in the destination allow-list"):
        assert_url_allowed("https://api.example.com", allowed_hosts=())


def test_none_keeps_the_legacy_deny_list_behaviour() -> None:
    """Existing callers that have not been configured must not change behaviour."""
    assert_url_allowed("https://api.example.com/x")
    with pytest.raises(SSRFBlockedError):
        assert_url_allowed("http://127.0.0.1:6185/api/health")


def test_an_allow_list_entry_cannot_authorise_a_private_address() -> None:
    """Allow-list first does not mean allow-list only."""
    with pytest.raises(SSRFBlockedError):
        assert_url_allowed(
            "http://127.0.0.1:6185/api/health", allowed_hosts=("127.0.0.1",)
        )


async def test_the_client_forwards_its_list_on_every_fetch(monkeypatch) -> None:
    """The list must reach the check at call time, not be baked in at construction.

    The spy raises so the request stops before DNS. What is under test is the argument
    the client passes, not the network path.
    """

    class _StopError(Exception):
        pass

    class _Guard:
        def check(self, *_args, **_kwargs) -> None:
            return None

    seen: dict[str, object] = {}

    def spy(url: str, *, allowed_hosts=None) -> None:
        seen["hosts"] = allowed_hosts
        raise _StopError

    monkeypatch.setattr(sandbox, "assert_url_allowed", spy)
    allowed = frozenset({"api.example.com"})
    client = SafeHttpClient(_Guard(), allowed_hosts=allowed)

    with pytest.raises(_StopError):
        await client.fetch("https://api.example.com/v1")
    assert seen["hosts"] == allowed

    client._allowed_hosts = frozenset({"rotated.example"})
    with pytest.raises(_StopError):
        await client.fetch("https://rotated.example/v1")
    assert seen["hosts"] == frozenset({"rotated.example"})

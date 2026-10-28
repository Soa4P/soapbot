"""Runtime enforcement of plugin capabilities.

The manifest *declares*; this module *enforces*. Two independent gates, both of
which must pass before a plugin API call is allowed:

1. **Declared** — the plugin listed the capability in its manifest.
2. **Approved** — the operator enabled that capability for this plugin.

Requiring both means a malicious manifest update cannot silently widen its own
reach: the plugin would have to also be re-approved. And a capability the plugin
never declared is refused even if the operator granted everything, because the
plugin's own code should not be able to exceed what it announced.

Why not rely on "the plugin only imports what it needs"?
--------------------------------------------------------
A plugin runs as ordinary Python. It can ``import httpx`` itself and bypass any
facade we hand it. We cannot prevent that in-process without OS-level sandboxing
(explicitly out of scope for v1). What this layer *can* do — and does — is:

* make the sanctioned path the only one that is convenient and observable,
* refuse the *declared-and-approved* path when it is not authorised, so a plugin
  cannot use the host's credentials, rate budget or user identity,
* produce an audit record for every sensitive operation, attributed to the plugin,
  so an operator can detect a plugin that misbehaves.

That limitation is documented rather than papered over; see
``docs/plugin-security.md`` §"残余风险".
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import re
import socket
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from soapbot.plugins.manifest import (
    RATE_LIMITED_CAPABILITIES,
    SENSITIVE_CAPABILITIES,
    Capability,
)
from soapbot.security.audit import AuditLog, get_audit_log
from soapbot.security.ratelimit import SlidingWindowLimiter

logger = logging.getLogger(__name__)


class CapabilityDeniedError(PermissionError):
    """Raised when a plugin tries something it may not do.

    Raised, never silently ignored: a plugin that receives a refused call must
    notice. Swallowing the error would let it continue as though it had received
    data, and would hide the attempt from the audit trail's cause.
    """

    def __init__(self, plugin: str, capability: Capability, reason: str) -> None:
        self.plugin = plugin
        self.capability = capability
        self.reason = reason
        super().__init__(f"plugin {plugin} denied {capability.value}: {reason}")


class PluginQuotaExceededError(RuntimeError):
    """Raised when a plugin exceeds its per-window operation budget."""


class _SealedObject:
    """Base class whose instances refuse attribute writes once sealed.

    This exists because the plugin-facing façade used to hand out plain mutable
    objects. A plugin could do::

        ctx._guard.grant = CapabilityGrant(..., approved=frozenset(Capability))

    and grant itself every capability — a **privilege escalation using only a
    public attribute assignment**, which was reproduced during the isolation
    review. "Approved by the operator" has to mean "not writable by the code being
    approved", otherwise it is an honour system.

    Honest limit, and the reason this class is not the whole answer: Python has no
    in-process way to stop ``object.__setattr__(obj, "_grant", ...)`` or
    ``ctypes``-level tampering. Sealing defeats accidental and opportunistic
    mutation, not a determined attacker with code execution in this interpreter.
    Only running the plugin in a separate process (see
    :mod:`soapbot.plugins.isolation`) makes the boundary unbypassable, which is why
    that module exists rather than being "future work".
    """

    __slots__ = ("_sealed",)

    def _seal(self) -> None:
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError(
                f"{type(self).__name__} is read-only after construction; "
                f"refusing to set {name!r}"
            )
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError(
                f"{type(self).__name__} is read-only after construction; "
                f"refusing to delete {name!r}"
            )
        object.__delattr__(self, name)


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    """The effective, audited grants for one plugin instance.

    Frozen: ``declared`` and ``approved`` are the two inputs to every authorisation
    decision, so they are immutable by construction. A mutable grant means the
    answer to "may this plugin use HTTP?" can change after the operator said no.
    """

    plugin: str
    declared: frozenset[Capability] = field(default_factory=frozenset)
    approved: frozenset[Capability] = field(default_factory=frozenset)

    @property
    def effective(self) -> frozenset[Capability]:
        return self.declared & self.approved

    def allows(self, capability: Capability) -> tuple[bool, str]:
        if capability not in self.declared:
            return False, "not declared in manifest"
        if capability not in self.approved:
            return False, "not approved by operator"
        return True, ""


class CapabilityGuard(_SealedObject):
    """Authorises and audits every capability use by one plugin.

    Sealed after construction: the guard is the object that *decides* whether a
    capability is allowed, so it must not be writable by the plugin it judges.
    Before this was sealed, ``ctx._guard.grant = <all capabilities>`` was a working
    self-escalation (reproduced during the isolation review).
    """

    __slots__ = ("_quota", "_sensitive_quota", "audit", "grant", "plugin")

    def __init__(
        self,
        grant: CapabilityGrant,
        *,
        audit: AuditLog | None = None,
        quota_per_minute: int = 120,
        sensitive_quota_per_minute: int = 30,
    ) -> None:
        self.grant = grant
        self.audit = audit or get_audit_log()
        self.plugin = grant.plugin
        # Separate budgets: a plugin's ordinary work must not be starved by, and
        # must not be able to subsidise, its sensitive operations.
        self._quota = SlidingWindowLimiter(limit=quota_per_minute, window_seconds=60)
        self._sensitive_quota = SlidingWindowLimiter(
            limit=sensitive_quota_per_minute, window_seconds=60
        )
        self._seal()

    def check(self, capability: Capability, *, detail: str = "") -> None:
        """Raise unless the plugin may use ``capability`` right now."""
        ok, reason = self.grant.allows(capability)
        if not ok:
            self.audit.record(
                kind="plugin",
                action=f"capability:{capability.value}",
                outcome="deny",
                detail=f"plugin={self.plugin} {reason}",
                plugin=self.plugin,
            )
            raise CapabilityDeniedError(self.plugin, capability, reason)

        limiter = (
            self._sensitive_quota
            if capability in SENSITIVE_CAPABILITIES or capability in RATE_LIMITED_CAPABILITIES
            else self._quota
        )
        result = limiter.check(self.plugin)
        if result.limited:
            self.audit.record(
                kind="rate_limit",
                action=f"plugin:{capability.value}",
                outcome="block",
                detail=f"plugin={self.plugin} retry_after={result.retry_after:.1f}s",
                plugin=self.plugin,
            )
            raise PluginQuotaExceededError(
                f"plugin {self.plugin} exceeded {capability.value} quota; "
                f"retry in {result.retry_after:.0f}s"
            )

        if capability in SENSITIVE_CAPABILITIES:
            # Sensitive use is *recorded on success too*: knowing a plugin sends
            # data outward is the whole point of the audit trail.
            self.audit.record(
                kind="plugin",
                action=f"capability:{capability.value}",
                outcome="allow",
                detail=f"plugin={self.plugin} {detail}".strip(),
                plugin=self.plugin,
            )


# --------------------------------------------------------------------- storage


_STORAGE_KEY_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,96}$")

#: Session keys look like ``adapter:scene:target`` (``onebot11:group:123456``).
#: This is deliberately *separate* from ``_STORAGE_KEY_RE``: reusing the storage
#: charset here rejected every real session key (it forbids ``:``), which made
#: ``ctx.send`` raise on 100% of calls. Security checks that reject all valid input
#: are indistinguishable from a missing feature until someone tries to use it.
_SESSION_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}:[a-z]{2,16}:[A-Za-z0-9_\-@.]{1,64}$")


class PluginStorage:
    """Per-plugin key-value namespace with no path component at all.

    Backed by a dict in v1 (persistence is a later concern), but the *access
    rules* are what matter and they are final:

    * keys are validated against a narrow charset, so ``../other/get`` or
      ``../../etc/passwd`` cannot be expressed;
    * the namespace is prefixed by plugin name at the storage boundary, so two
      plugins writing ``token`` never collide and never read each other;
    * the plugin is handed a bound view whose prefix it cannot see or change,
      and the underlying mapping is never exposed by reference.
    """

    def __init__(self, plugin: str, backend: dict[str, dict[str, Any]]) -> None:
        self._plugin = plugin
        # Hold *only this plugin's* namespace, not the whole backend.
        #
        # The previous version kept a reference to the shared outer dict, which
        # meant ``storage._backend["other_plugin"]["api_token"]`` read another
        # plugin's secret straight out of the in-memory store — reproduced during
        # the isolation review. Namespace isolation that lives only in the key
        # prefix is not isolation: the prefix is one dictionary lookup away from
        # being ignored.
        self._backend = backend.setdefault(plugin, {})

    def _key(self, key: str) -> str:
        if not isinstance(key, str) or not _STORAGE_KEY_RE.match(key):
            raise ValueError(
                "storage key must match ^[A-Za-z0-9_.-]{1,96}$ "
                "(no slashes, no '..', no control characters)"
            )
        if ".." in key:
            raise ValueError("storage key must not contain '..'")
        return key

    def get(self, key: str, default: Any = None) -> Any:
        return self._backend.get(self._key(key), default)

    def set(self, key: str, value: Any) -> None:
        # Values must be JSON-representable; refusing arbitrary objects stops a
        # plugin storing a live object reference that later code would trust.
        try:
            import json

            json.dumps(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("storage values must be JSON-serialisable") from exc
        self._backend[self._key(key)] = value

    def delete(self, key: str) -> None:
        self._backend.pop(self._key(key), None)

    def keys(self) -> list[str]:
        return sorted(self._backend)

    def all(self) -> dict[str, Any]:
        """A copy, so a plugin cannot mutate the store through the returned dict."""
        return dict(self._backend)


class EncryptedPluginStorage(PluginStorage):
    """Storage whose values are encrypted at rest.

    Used for plugin-declared secrets (API tokens the plugin needs). Encrypting at
    the storage boundary means a database dump or a stray ``*.db`` backup does not
    hand over every plugin's credentials in plaintext.
    """

    def __init__(self, plugin: str, backend: dict[str, dict[str, Any]], crypto) -> None:
        super().__init__(plugin, backend)
        self._crypto = crypto

    def set(self, key: str, value: Any) -> None:
        import json

        try:
            blob = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("storage values must be JSON-serialisable") from exc
        self._backend[self._key(key)] = self._crypto.encrypt(blob)

    def get(self, key: str, default: Any = None) -> Any:
        import json

        raw = self._backend.get(self._key(key))
        if raw is None:
            return default
        if not isinstance(raw, str):
            # Written before encryption was enabled; treat as untrusted legacy.
            return default
        try:
            return json.loads(self._crypto.decrypt(raw))
        except Exception:
            logger.warning(
                "plugin secret decrypt failed plugin=%s key=%s", self._plugin, key
            )
            return default


# ------------------------------------------------------------------------ http


_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata",
        "metadata.google.internal",
        "metadata.azure.com",
        "instance-data",
        "instance-data.ec2.internal",
    }
)

_BLOCKED_PORTS = frozenset({22, 23, 25, 445, 1433, 3306, 5432, 6379, 9200, 11211})

#: Networks that must never be reachable from a plugin, beyond what
#: ``ipaddress.is_private`` already covers.
#:
#: **Why this list has to exist.** ``is_private`` follows the IANA special-purpose
#: registry for most ranges but does *not* flag 100.64.0.0/10 (carrier-grade NAT).
#: That range contains the Alibaba Cloud metadata service at **100.100.100.200**,
#: which hands out instance credentials. An earlier version of this file relied on
#: ``is_private`` alone and allowed it through — a working SSRF path to cloud
#: credentials. Explicit networks are used rather than more ``is_*`` flags because a
#: future Python release can change what those flags mean; a named CIDR cannot
#: silently stop matching.
_BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT — holds Alibaba/Azure metadata
    ipaddress.ip_network("192.0.0.0/24"),  # IETF protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.ip_network("198.18.0.0/15"),  # benchmarking
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("192.88.99.0/24"),  # 6to4 relay anycast
    ipaddress.ip_network("240.0.0.0/4"),  # reserved, incl. broadcast
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),  # unique local
    ipaddress.ip_network("fe80::/10"),  # link local
    ipaddress.ip_network("ff00::/8"),  # multicast
    ipaddress.ip_network("64:ff9b::/96"),  # NAT64 — reaches IPv4 space
    ipaddress.ip_network("2002::/16"),  # 6to4 — embeds an IPv4 address
)


class SSRFBlockedError(ValueError):
    """Raised when a plugin tries to reach an address it must not."""


def assert_url_allowed(url: str) -> None:
    """Reject URLs that reach private/infrastructure addresses.

    Threat: a plugin with ``HTTP`` capability is an SSRF primitive. Without this
    check it can read the cloud metadata service (``169.254.169.254``), the bot's
    own admin API on ``127.0.0.1:6185``, or a database on ``10.0.0.0/8`` — using
    the bot's network position, which the plugin author does not otherwise have.

    Checks performed on the literal URL *and* on the resolved IPs, because a
    hostname can resolve to a private address (DNS rebinding is mitigated by
    connecting to the vetted IP; see :class:`SafeHttpClient`).
    """
    if not url or not isinstance(url, str):
        raise SSRFBlockedError("url must be a non-empty string")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise SSRFBlockedError(f"scheme {parts.scheme!r} is not allowed")
    if not parts.hostname:
        raise SSRFBlockedError("url has no host")

    host = parts.hostname.lower().strip(".")
    if host in _BLOCKED_HOSTNAMES:
        raise SSRFBlockedError(f"host {host!r} is blocked")
    if host.endswith(".internal") or host.endswith(".local"):
        raise SSRFBlockedError(f"host {host!r} is a private namespace")

    if parts.port and parts.port in _BLOCKED_PORTS:
        raise SSRFBlockedError(f"port {parts.port} is blocked")

    # Literal IP? Use the strictest reading and also reject IP-ish text that
    # ``ipaddress`` cannot parse but an HTTP stack might, e.g. ``127.1`` (classful
    # shorthand), ``2130706433`` (single integer) and ``0x7f.0.0.1`` (hex). These
    # resolve to loopback on many platforms. ``resolve_and_verify`` catches them on
    # Linux via getaddrinfo, but not everywhere — and a host that *does* parse them
    # would otherwise be contacted, so the literal check must not depend on the
    # resolver's opinion.
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None
    if addr is not None:
        _assert_ip_public(addr, host)
    elif _looks_like_ip_literal(host):
        raise SSRFBlockedError(
            f"host {host!r} is an ambiguous numeric address; use a canonical IP "
            "or a DNS name"
        )

    # Userinfo in the URL is a classic filter-bypass trick:
    # http://allowed.example@169.254.169.254/
    if parts.username or parts.password:
        raise SSRFBlockedError("credentials in URL are not allowed")


def _looks_like_ip_literal(host: str) -> bool:
    """True for host strings that are IP addresses written in a non-canonical way.

    Covers: all-numeric (``2130706433``), dotted-shorthand (``127.1``), hex/octal
    octets (``0x7f.0.0.1``, ``0177.0.0.1``) and the same with a trailing dot. A
    genuine hostname must contain a letter or a hyphen, so anything made purely of
    hex digits, dots and an optional ``0x`` prefix is treated as numeric.
    """
    candidate = host.rstrip(".")
    if not candidate:
        return False
    if re.fullmatch(r"\d{1,12}", candidate):
        return True
    if re.fullmatch(r"0x[0-9a-f]+(\.[0-9a-f]+)*", candidate):
        return True
    return bool(re.fullmatch(r"[\d.]+", candidate))


def _assert_ip_public(addr: ipaddress.IPv4Address | ipaddress.IPv6Address, host: str) -> None:
    """Reject any address that is not clearly public internet.

    Order matters: an IPv6 address that *embeds* an IPv4 address (``::ffff:127.0.0.1``,
    NAT64, 6to4) is unwrapped and checked as IPv4 first. Checking only the outer
    IPv6 form would let ``::ffff:169.254.169.254`` through, because the IPv6 view of
    it is a global unicast address.
    """
    # Unwrap IPv4-in-IPv6 so the IPv4 rules apply to what is actually contacted.
    if isinstance(addr, ipaddress.IPv6Address):
        mapped = addr.ipv4_mapped or addr.sixtofour or getattr(addr, "teredo", None)
        if mapped is not None:
            _assert_ip_public(ipaddress.IPv4Address(mapped), host)
            return

    if any(addr in net for net in _BLOCKED_NETWORKS):
        raise SSRFBlockedError(f"address {host} is in a blocked range")

    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    ):
        raise SSRFBlockedError(f"address {host} is in a blocked range")

    # Belt and braces: anything ipaddress does not consider globally routable is
    # refused. `is_global` is the positive test; requiring it means a *new* special
    # purpose range introduced by a future IANA registry fails closed by default.
    if not addr.is_global:
        raise SSRFBlockedError(f"address {host} is not globally routable")


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _pin_url_to_ip(parts, ip: str) -> str:
    """Rebuild a URL that targets ``ip`` while preserving path and query.

    IPv6 literals must be bracketed in the authority, otherwise the colons are
    parsed as a port separator and the request goes to the wrong place.
    """
    authority = f"[{ip}]" if ":" in ip else ip
    if parts.port:
        authority = f"{authority}:{parts.port}"
    path = parts.path or "/"
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme}://{authority}{path}{query}"


async def resolve_and_verify(host: str) -> list[str]:
    """Resolve ``host`` and reject if any answer is private.

    All answers are checked, not just the first: a host with A records
    ``1.2.3.4`` and ``127.0.0.1`` would otherwise pass on a lucky lookup. The
    caller then connects to one of the returned addresses directly, so a second
    resolution (and the rebinding window it opens) never happens.
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SSRFBlockedError(f"cannot resolve {host}: {exc}") from exc
    addrs: list[str] = []
    for info in infos:
        raw = info[4][0]
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            continue
        _assert_ip_public(addr, raw)
        addrs.append(raw)
    if not addrs:
        raise SSRFBlockedError(f"no usable address for {host}")
    return addrs


class SafeHttpClient:
    """Outbound HTTP for plugins, with SSRF defence and strict limits.

    Deliberate restrictions, each closing a concrete abuse path:

    * **No redirects.** A redirect to ``http://169.254.169.254/`` would otherwise
      walk straight past the pre-flight URL check, since only the first hop was
      validated.
    * **Response size cap.** A plugin streaming a 10 GB body into memory is a
      denial of service against the whole bot process.
    * **Timeout cap.** Same reason, with sockets instead of RAM.
    * **Header allow-list.** A plugin must not be able to set ``Host``,
      ``Authorization`` for the *bot's* credentials, or hop-by-hop headers that
      would turn it into a proxy.
    """

    ALLOWED_REQUEST_HEADERS = frozenset(
        {"accept", "accept-language", "content-type", "user-agent", "referer"}
    )
    MAX_RESPONSE_BYTES = 2 * 1024 * 1024
    MAX_TIMEOUT = 15.0

    def __init__(self, guard: CapabilityGuard, *, client_factory=None) -> None:
        self._guard = guard
        self._client_factory = client_factory

    def _sanitize_headers(self, headers: dict[str, str] | None) -> dict[str, str]:
        """Allow-list only, and fail loudly on anything else.

        Two failure modes to avoid, both worse than being strict:

        * **silently dropping** an unknown header — the plugin believes it set a
          header it did not, and debugging that costs more than a clear error;
        * **passing through** ``Host``/``Authorization``/``Cookie`` — the first
          forges the request target, the last two would attach the bot's own
          credentials to a destination the plugin chose.
        """
        out: dict[str, str] = {}
        for key, value in (headers or {}).items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError("headers must be str->str")
            lowered = key.lower().strip()
            if lowered in ("host", "authorization", "cookie", "content-length"):
                raise ValueError(f"header {key!r} is not allowed from plugins")
            if "\n" in value or "\r" in value:
                # Request smuggling via CRLF in a header value.
                raise ValueError("header values must not contain newlines")
            if lowered not in self.ALLOWED_REQUEST_HEADERS:
                raise ValueError(
                    f"header {key!r} is not in the allow-list "
                    f"({', '.join(sorted(self.ALLOWED_REQUEST_HEADERS))})"
                )
            out[key] = value
        return out

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = 10.0,
    ) -> tuple[int, bytes]:
        self._guard.check(Capability.HTTP, detail=f"{method} {urlsplit(url).netloc}")
        assert_url_allowed(url)
        parts = urlsplit(url)
        host = parts.hostname or ""
        vetted = await resolve_and_verify(host)

        if body is not None and len(body) > 1024 * 1024:
            raise ValueError("request body exceeds 1 MiB")
        timeout = min(max(0.1, float(timeout)), self.MAX_TIMEOUT)
        safe_headers = self._sanitize_headers(headers)

        # --- TOCTOU close: connect to the IP we vetted, not to the name again ---
        # ``resolve_and_verify`` above proves the name mapped to public addresses at
        # that instant. If we then hand the *name* to httpx, it resolves again, and
        # a rebinding host can answer with 127.0.0.1 the second time. Pinning the
        # connection to ``vetted[0]`` while keeping the original Host header (set
        # explicitly below, since plugins may not set it themselves) removes the
        # second lookup entirely.
        pinned_url = _pin_url_to_ip(parts, vetted[0])
        send_headers = dict(safe_headers)
        # Preserve SNI/Host correctness for name-based virtual hosting.
        send_headers["Host"] = parts.netloc.rsplit("@", 1)[-1]

        factory = self._client_factory
        if factory is None:
            import httpx

            client = httpx.AsyncClient(
                follow_redirects=False,  # see class docstring
                timeout=timeout,
                trust_env=False,  # ignore proxy env vars: they bypass our checks
            )
        else:  # pragma: no cover - test seam
            client = factory(timeout=timeout)

        request_kwargs: dict[str, Any] = {
            "headers": send_headers,
            "content": body,
        }
        if not _is_ip(host):
            # Keep TLS certificate validation pointed at the original name even
            # though we connect by IP, otherwise verification would compare the
            # certificate against the IP and fail (or, worse, be disabled).
            request_kwargs["extensions"] = {"sni_hostname": host}

        try:
            resp = await client.request(method.upper(), pinned_url, **request_kwargs)
            data = resp.content
            if len(data) > self.MAX_RESPONSE_BYTES:
                data = data[: self.MAX_RESPONSE_BYTES]
            if 300 <= resp.status_code < 400:
                # Surfaced as a failure rather than followed, so a plugin cannot
                # use a redirect chain to reach a blocked address.
                raise SSRFBlockedError(
                    f"redirect to {resp.headers.get('location', '?')!r} not followed"
                )
            return resp.status_code, data
        finally:
            aclose = getattr(client, "aclose", None)
            if aclose is not None:
                await aclose()


# ------------------------------------------------------------ output validation


_SECRET_IN_TEXT_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}"
    r"|(?i:bearer)\s+[A-Za-z0-9._\-]{8,}"
    r"|(?i:(api[_-]?key|token|secret|password|passwd))"
    r"\s*[=:]\s*\S{6,})"
)


def scrub_plugin_output(text: str, *, max_chars: int = 4000) -> str:
    """Clean a string a plugin wants to send to a chat.

    A plugin is a data path *out* of the bot. Whatever it produces will be shown
    to group members, so this applies the same rules the core reply path applies:

    * strip invisible/bidi characters (used to smuggle instructions or to make a
      message *look* like something else in logs);
    * truncate to the same budget the core uses, so a plugin cannot flood a group;
    * mask anything that looks like a credential — a plugin echoing its own
      config into chat must not thereby publish the operator's API key.
    """
    from soapbot.security.injection import neutralise_markup, redact, strip_invisible

    if not isinstance(text, str):
        raise TypeError("plugin output must be a string")
    cleaned = strip_invisible(text)
    cleaned = redact(cleaned)
    cleaned = _SECRET_IN_TEXT_RE.sub("***REDACTED***", cleaned)
    # Plugin output reaches: the chat client, the WebUI log/debug panes, and the
    # audit trail. All three render or store attacker-influenced strings, so markup
    # is neutralised here rather than trusting each consumer to escape.
    cleaned = neutralise_markup(cleaned)
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "…"
    return cleaned


def validate_command_name(name: str) -> str:
    """Command names land in the shared dispatcher, so they are validated.

    Rejects names that would shadow core commands, contain path or shell
    metacharacters, or be invisible to the user but distinct to the matcher
    (full-width slashes, zero-width joiners).
    """
    if not isinstance(name, str):
        raise ValueError("command name must be a string")
    lowered = name.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_\-]{0,31}", lowered):
        raise ValueError(
            "command name must match ^[a-z][a-z0-9_-]{0,31}$ (lowercase, no spaces)"
        )
    if lowered in CORE_COMMANDS:
        raise ValueError(f"command {lowered!r} is reserved by the core")
    return lowered


#: Core command names that plugins must not override. Taken from
#: ``CommandStage.COMMAND_PERMISSIONS``; duplicated here as a literal so the
#: plugin layer has no import dependency on the memory package.
CORE_COMMANDS: frozenset[str] = frozenset(
    {"recall", "timeline", "forget", "kb", "help", "ping", "budget", "bili"}
)


@dataclass(slots=True)
class PluginInvocation:
    """Audit record shape for one plugin call."""

    plugin: str
    entry: str
    ok: bool
    duration_ms: float
    error: str = ""
    started: float = field(default_factory=time.time)


def fingerprint_code(code: bytes) -> str:
    """Digest of plugin source, so the WebUI can show *which build* is running.

    Not a security control on its own — a plugin can import other files — but it
    makes "the plugin changed since you approved its capabilities" visible.
    """
    return hashlib.sha256(code).hexdigest()[:16]

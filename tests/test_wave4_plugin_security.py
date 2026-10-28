"""Plugin security: manifest attacks, capability bypass, SSRF, secret leakage.

Each test states the attack and the observable that proves it failed. The bar for
"proven" is an *effect*: an exception raised, a value absent, a call not made —
never an internal flag that could be true while behaviour is unchanged.

Attack classes
--------------
  A. Malicious manifest   — path traversal, code-injection entry, YAML RCE,
                            dependency auto-install, name/dir mismatch
  B. Capability bypass    — undeclared use, unapproved use, quota abuse
  C. SSRF / egress        — metadata service, loopback, redirect, credentials,
                            DNS answer to a private range
  D. Secret handling      — encryption at rest, no plaintext in storage/audit/log,
                            output scrubbing, cross-plugin isolation
  E. Data path out        — command/tool output scrubbing, canary leak, length
  F. Load/unload control  — implicit load refused, untrusted+sensitive refused,
                            failed reload, directory deletion containment
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from soapbot.plugins.context import PluginContext
from soapbot.plugins.loader import PluginLoader, PluginLoadError
from soapbot.plugins.manifest import (
    Capability,
    ManifestError,
    parse_manifest,
)
from soapbot.plugins.sandbox import (
    CapabilityDeniedError,
    CapabilityGrant,
    CapabilityGuard,
    PluginQuotaExceededError,
    PluginStorage,
    SSRFBlockedError,
    assert_url_allowed,
    scrub_plugin_output,
    validate_command_name,
)
from soapbot.security.audit import AuditLog
from soapbot.security.crypto import SecretBox

VALID = {
    "name": "demo",
    "version": "1.0.0",
    "entry": "main:DemoPlugin",
}


# ------------------------------------------------------- A. malicious manifest


@pytest.mark.parametrize(
    "name",
    [
        "../../etc/cron.d/evil",
        "..",
        "../sibling",
        "a/b",
        "a\\b",
        "demo\x00",
        "DEMO",
        "-leading-dash",
        "1numeric",
        "",
        "x" * 60,
        "demo;rm -rf /",
    ],
)
def test_path_traversal_and_bad_names_are_rejected(name: str) -> None:
    """The plugin name becomes a directory name and a storage namespace.

    ``../../etc/cron.d/evil`` as a name is a file-write primitive outside the
    plugins directory; the charset restriction is what stops it.
    """
    with pytest.raises(ManifestError):
        parse_manifest({**VALID, "name": name})


@pytest.mark.parametrize(
    "entry",
    [
        "os:system",
        "subprocess:Popen",
        "sys:modules",
        "__import__:x",
        "main",  # no attribute
        "main:",  # empty attribute
        ":attr",  # empty module
        "main:attr;os.system('id')",
        "main:attr\nimport os",
        "main:__class__",
        "..main:attr",
        "/abs/path/main:attr",
        "main.sub:attr.more",
    ],
)
def test_hostile_entry_points_are_rejected(entry: str) -> None:
    """The entry string is passed to the import machinery.

    ``os:system`` is the classic gadget: if the loader ever imported the entry
    verbatim it would hand back a callable into ``os``. Rejecting at parse time
    means the loader never sees it.
    """
    with pytest.raises(ManifestError):
        parse_manifest({**VALID, "entry": entry})


def test_yaml_python_object_tag_is_not_executed(tmp_path: Path) -> None:
    """A manifest using ``!!python/object/apply`` must not run code.

    ``yaml.load`` with the unsafe loader turns *parsing a file* into code
    execution — before any validation, before approval. The loader uses
    ``safe_load``, so the tag is refused instead of honoured.
    """
    plugin_dir = tmp_path / "plugins" / "evil"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.yaml").write_text(
        "name: evil\n"
        "version: '1.0.0'\n"
        "entry: main:P\n"
        "payload: !!python/object/apply:os.system ['echo pwned > /tmp/pwned']\n",
        encoding="utf-8",
    )
    loader = PluginLoader(plugins_dir=tmp_path / "plugins", audit=AuditLog())
    report = loader.discover()

    assert report.found == []
    assert any("malformed" in reason or "YAML" in reason for _, reason in report.rejected)


@pytest.mark.parametrize(
    "requires",
    [
        ["requests @ https://evil.example/pkg.tar.gz"],
        ["git+https://evil.example/repo.git"],
        ["pkg; rm -rf /"],
        ["pkg\nother"],
        ["../../etc/passwd"],
        ["pkg==1.0 --index-url http://evil"],
    ],
)
def test_dependency_urls_and_injection_are_rejected(requires: list[str]) -> None:
    """Dependencies are declarations, never install instructions.

    A URL/VCS reference bypasses any index review, so "install my plugin" would
    become "fetch and run this tarball of my choosing".
    """
    with pytest.raises(ManifestError):
        parse_manifest({**VALID, "requires": requires})


def test_unknown_capability_is_rejected_not_ignored() -> None:
    """A typo'd capability must fail loudly.

    Ignoring ``"HTTR"`` would leave a plugin believing it holds a permission it
    does not — and the equivalent mistake in the other direction would grant one
    it never asked for.
    """
    with pytest.raises(ManifestError) as exc:
        parse_manifest({**VALID, "capabilities": ["command", "HTTR"]})
    assert "unknown capability" in str(exc.value)


def test_control_characters_in_metadata_are_rejected() -> None:
    """Newlines in ``author`` are log injection: they forge a second log line."""
    with pytest.raises(ManifestError):
        parse_manifest({**VALID, "author": "x\n2026-01-01 INFO trusted plugin loaded"})


def test_manifest_name_must_match_directory(tmp_path: Path) -> None:
    """Two sources of truth for "which plugin is this" is a confusion bug.

    Storage namespacing uses the manifest name; the loader looks the plugin up by
    directory name. A mismatch means a plugin could write into another's storage
    namespace.
    """
    plugin_dir = tmp_path / "plugins" / "actual_dir"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.yaml").write_text(
        "name: other_name\nversion: '1.0.0'\nentry: main:P\n", encoding="utf-8"
    )
    loader = PluginLoader(plugins_dir=tmp_path / "plugins", audit=AuditLog())
    report = loader.discover()
    assert report.found == []
    assert any("does not match directory" in r for _, r in report.rejected)


def test_newer_host_requirement_is_refused() -> None:
    """A plugin needing a future host API is refused at load, not at first use.

    Deferring the error means an ``AttributeError`` fires inside a handler while
    serving a real user, which is both unreproducible and a poor place to discover
    an incompatibility.
    """
    from soapbot.plugins.manifest import check_host_compatibility

    manifest = parse_manifest({**VALID, "min_host_version": "99.0.0"})
    with pytest.raises(ManifestError) as exc:
        check_host_compatibility(manifest, "0.1.0")
    assert "requires host" in str(exc.value)


def test_compatible_host_requirement_passes() -> None:
    from soapbot.plugins.manifest import check_host_compatibility

    manifest = parse_manifest({**VALID, "min_host_version": "0.1.0"})
    check_host_compatibility(manifest, "0.3.0")  # must not raise


def test_symlinked_plugin_dir_is_rejected(tmp_path: Path) -> None:
    """A symlink makes the loader import code from outside the plugins root."""
    root = tmp_path / "plugins"
    root.mkdir()
    outside = tmp_path / "elsewhere" / "real"
    outside.mkdir(parents=True)
    (outside / "plugin.yaml").write_text(
        "name: real\nversion: '1.0.0'\nentry: main:P\n", encoding="utf-8"
    )
    try:
        (root / "real").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this platform")

    loader = PluginLoader(plugins_dir=root, audit=AuditLog())
    report = loader.discover()
    assert report.found == []
    assert any("symlink" in r for _, r in report.rejected)


# ---------------------------------------------------------- B. capability bypass


def _guard(declared: set[Capability], approved: set[Capability], audit=None) -> CapabilityGuard:
    return CapabilityGuard(
        CapabilityGrant(
            plugin="demo", declared=frozenset(declared), approved=frozenset(approved)
        ),
        audit=audit or AuditLog(),
    )


def test_undeclared_capability_is_denied() -> None:
    """The plugin never announced HTTP, so it may not use it."""
    guard = _guard({Capability.COMMAND}, {Capability.COMMAND})
    with pytest.raises(CapabilityDeniedError) as exc:
        guard.check(Capability.HTTP)
    assert "not declared" in str(exc.value)


def test_unapproved_capability_is_denied() -> None:
    """Declared but not granted by the operator: still refused.

    This is the gate that survives a malicious manifest update: the plugin can
    write whatever it likes into its own manifest, but approval lives in the
    host's state.
    """
    guard = _guard({Capability.HTTP}, {Capability.COMMAND})
    with pytest.raises(CapabilityDeniedError) as exc:
        guard.check(Capability.HTTP)
    assert "not approved" in str(exc.value)


def test_capability_denial_is_audited() -> None:
    audit = AuditLog()
    guard = _guard({Capability.COMMAND}, set(), audit=audit)
    with pytest.raises(CapabilityDeniedError):
        guard.check(Capability.HTTP)
    assert audit.denials >= 1
    assert any(e["kind"] == "plugin" for e in audit.recent())


def test_sensitive_use_is_audited_on_success_too() -> None:
    """Knowing a plugin sends data outward is the point of the trail."""
    audit = AuditLog()
    guard = _guard({Capability.HTTP}, {Capability.HTTP}, audit=audit)
    guard.check(Capability.HTTP, detail="GET example.com")
    events = [e for e in audit.recent() if e["kind"] == "plugin"]
    assert any(e["outcome"] == "allow" and "http" in e["action"] for e in events)


def test_sensitive_quota_is_enforced() -> None:
    guard = CapabilityGuard(
        CapabilityGrant(
            plugin="demo",
            declared=frozenset({Capability.HTTP}),
            approved=frozenset({Capability.HTTP}),
        ),
        audit=AuditLog(),
        sensitive_quota_per_minute=2,
    )
    guard.check(Capability.HTTP)
    guard.check(Capability.HTTP)
    with pytest.raises(PluginQuotaExceededError):
        guard.check(Capability.HTTP)


def test_registration_requires_capability() -> None:
    """A plugin without COMMAND cannot register a command.

    Checked at registration rather than dispatch, so a plugin cannot even build a
    surface it lacks the right to expose.
    """
    guard = _guard(set(), set())
    ctx = PluginContext(plugin="demo", guard=guard)
    with pytest.raises(CapabilityDeniedError):
        ctx.command("test")(lambda c, a: None)


def test_core_command_names_cannot_be_taken() -> None:
    """A plugin must not shadow ``/forget``.

    An override would be a security regression: the core command's handler and
    its permission check would be replaced by plugin code.
    """
    for core in ("forget", "kb", "recall", "timeline", "help", "ping"):
        with pytest.raises(ValueError):
            validate_command_name(core)


@pytest.mark.parametrize(
    "name",
    ["with space", "/slash", "dot.name", "a" * 40, "esc\x1b[31m", "", "命令", "a:b"],
)
def test_command_name_validation(name: str) -> None:
    with pytest.raises(ValueError):
        validate_command_name(name)


def test_command_name_is_lowercased_not_rejected() -> None:
    """Case is normalised rather than refused: ``/Echo`` and ``/echo`` are the same
    command to a user, so accepting either is correct as long as they cannot become
    two distinct registrations."""
    assert validate_command_name("Echo") == "echo"
    assert validate_command_name("  MiXeD  ") == "mixed"


# ------------------------------------------------------------------ C. SSRF


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "http://127.0.0.1:6185/api/security/audit",
        "http://localhost/admin",
        "http://[::1]/",
        "http://10.0.0.5/internal",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://0.0.0.0/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "file:///etc/passwd",
        "gopher://evil/",
        "http://user:pass@evil.example/",
        "http://redis.internal:6379/",
    ],
)
def test_ssrf_targets_are_blocked(url: str) -> None:
    """A plugin holding HTTP is an SSRF primitive: block the obvious targets.

    The metadata service and the bot's own API are the two that matter most — the
    first hands out cloud credentials, the second is an unauthenticated local
    admin interface.
    """
    with pytest.raises(SSRFBlockedError):
        assert_url_allowed(url)


@pytest.mark.parametrize(
    "url",
    ["https://api.example.com/v1/items", "http://example.com/", "https://1.1.1.1/"],
)
def test_public_urls_are_allowed(url: str) -> None:
    """Guard-rail: the check must not block ordinary internet access."""
    assert_url_allowed(url)


async def test_dns_answer_to_private_range_is_blocked() -> None:
    """A public-looking hostname that resolves to a private address is refused.

    All answers are checked, not just the first, because a host can return both a
    public and a private record.
    """
    from soapbot.plugins.sandbox import resolve_and_verify

    with pytest.raises(SSRFBlockedError):
        await resolve_and_verify("localhost")


async def test_http_client_requires_capability() -> None:
    from soapbot.plugins.sandbox import SafeHttpClient

    client = SafeHttpClient(_guard(set(), set()))
    with pytest.raises(CapabilityDeniedError):
        await client.fetch("https://example.com/")


async def test_http_client_rejects_forbidden_headers() -> None:
    """A plugin must not forge Host or attach the bot's Authorization header."""
    from soapbot.plugins.sandbox import SafeHttpClient

    client = SafeHttpClient(_guard({Capability.HTTP}, {Capability.HTTP}))
    with pytest.raises(ValueError):
        await client.fetch("https://example.com/", headers={"Host": "evil"})
    with pytest.raises(ValueError):
        await client.fetch("https://example.com/", headers={"Authorization": "Bearer x"})
    with pytest.raises(ValueError):
        await client.fetch("https://example.com/", headers={"X-Test": "a\r\nInjected: 1"})


# ---------------------------------------------------- D. secrets & isolation


#: A real Fernet key. Using a fake 44-byte string here would fail inside
#: ``Fernet()`` and the test would pass for the wrong reason — asserting the
#: constructor rejects junk rather than that storage encrypts.
TEST_KEY = b"anEqA6vBsp9UxvtWxfviD78MNZ3PAIB2_G6AY8zDepY="
TEST_KEY_2 = b"Zm9vYmFyYmF6cXV1eGNvcmdlZ3JhdWx0Z2FycGx5Z2g="


def test_storage_is_encrypted_at_rest() -> None:
    """A plugin's stored token must not be readable from the raw backend."""
    box = SecretBox(key=TEST_KEY)
    backend: dict[str, dict] = {}
    from soapbot.plugins.sandbox import EncryptedPluginStorage

    store = EncryptedPluginStorage("demo", backend, box)
    store.set("api_token", "sk-super-secret-value")

    raw = backend["demo"]["api_token"]
    assert "sk-super-secret-value" not in raw
    assert raw.startswith("enc:v1:")
    assert store.get("api_token") == "sk-super-secret-value"


def test_storage_namespaces_are_isolated() -> None:
    """Two plugins writing ``token`` must not see each other's value."""
    backend: dict[str, dict] = {}
    a = PluginStorage("plugin_a", backend)
    b = PluginStorage("plugin_b", backend)
    a.set("token", "A-value")
    b.set("token", "B-value")
    assert a.get("token") == "A-value"
    assert b.get("token") == "B-value"
    assert a.keys() == ["token"]


@pytest.mark.parametrize(
    "key",
    ["../other/secret", "a/b", "..", "\x00", "key\nline", "x" * 200],
)
def test_storage_key_traversal_is_refused(key: str) -> None:
    """Storage keys have no path semantics, so they must not look like paths."""
    store = PluginStorage("demo", {})
    with pytest.raises(ValueError):
        store.set(key, "v")


def test_storage_rejects_non_json_values() -> None:
    """Storing a live object would let a plugin hand later code a trusted reference."""
    store = PluginStorage("demo", {})
    with pytest.raises(ValueError):
        store.set("obj", object())


def test_storage_all_returns_a_copy() -> None:
    """Mutating the returned dict must not write through to the store."""
    store = PluginStorage("demo", {})
    store.set("k", 1)
    snapshot = store.all()
    snapshot["k"] = 999
    assert store.get("k") == 1


def test_plugin_secret_never_appears_in_audit() -> None:
    """The audit log is streamed to the browser; secrets must not ride along."""
    audit = AuditLog()
    audit.record(
        kind="plugin",
        action="capability:http",
        outcome="allow",
        plugin="demo",
        token="sk-abcdefghijklmnop",
        api_key="another-secret-value",
    )
    dumped = str(audit.recent())
    assert "sk-abcdefghijklmnop" not in dumped
    assert "another-secret-value" not in dumped


def test_encrypted_storage_roundtrip_with_wrong_key_fails() -> None:
    """Wrong key must raise, not silently return junk that callers might trust."""
    box1 = SecretBox(key=TEST_KEY)
    box2 = SecretBox(key=TEST_KEY_2)
    backend: dict[str, dict] = {}
    from soapbot.plugins.sandbox import EncryptedPluginStorage

    EncryptedPluginStorage("demo", backend, box1).set("k", "value")
    reader = EncryptedPluginStorage("demo", backend, box2)
    # get() swallows the failure and returns the default: a plugin must not
    # receive a half-decrypted value.
    assert reader.get("k", "fallback") == "fallback"
    with pytest.raises(ValueError):
        box2.decrypt(backend["demo"]["k"])


# ------------------------------------------------------------ E. data path out


@pytest.mark.parametrize(
    "text,secret",
    [
        ("key is sk-abcdefghijklmnop", "sk-abcdefghijklmnop"),
        ("token=supersecretvalue123", "supersecretvalue123"),
        ("Authorization: Bearer abcdefghijklmnop", "abcdefghijklmnop"),
    ],
)
def test_plugin_output_masks_secrets(text: str, secret: str) -> None:
    """A plugin echoing its config into chat must not publish the key.

    The plugin cannot be trusted to sanitise its own output; the host does it on
    the way out for every plugin reply.
    """
    out = scrub_plugin_output(text)
    assert secret not in out
    assert "REDACTED" in out


def test_plugin_output_strips_invisible_characters() -> None:
    """Zero-width characters are used to smuggle instructions past readers."""
    out = scrub_plugin_output("正\u200b常\u200b文\u200b本")
    assert "\u200b" not in out
    assert "正常文本" in out


def test_plugin_output_is_length_capped() -> None:
    """A plugin must not be able to flood a group.

    The cap matches the core reply budget, so plugins have no larger voice than
    the bot itself.
    """
    out = scrub_plugin_output("x" * 10000, max_chars=100)
    assert len(out) <= 101


def test_plugin_output_type_is_checked() -> None:
    with pytest.raises(TypeError):
        scrub_plugin_output(123)  # type: ignore[arg-type]


def test_canary_in_plugin_output_is_detected() -> None:
    """If a plugin forwards retrieved/model text verbatim, the canary shows up."""
    from soapbot.security.injection import leaked_canary, wrap_untrusted

    wrapped = wrap_untrusted("恶意内容", kind="memory")
    assert leaked_canary(scrub_plugin_output(wrapped)) is True


# ------------------------------------------------- F. load / unload control


async def _make_plugin(root: Path, name: str, *, capabilities: list[str], trust: str = "untrusted",
                       body: str = "class P:\n    def setup(self, ctx):\n        pass\n") -> Path:
    d = root / name
    d.mkdir(parents=True)
    caps = "".join(f"  - {c}\n" for c in capabilities)
    (d / "plugin.yaml").write_text(
        f"name: {name}\nversion: '1.0.0'\nentry: main:P\n"
        f"trust: {trust}\ncapabilities:\n{caps}",
        encoding="utf-8",
    )
    (d / "main.py").write_text(body, encoding="utf-8")
    return d


async def test_plugin_is_not_loaded_without_approval(tmp_path: Path) -> None:
    """Discovery must not equal execution.

    Anything that can write to ``data/plugins`` would otherwise get code execution
    on the next restart.
    """
    root = tmp_path / "plugins"
    await _make_plugin(root, "sneaky", capabilities=["command"])

    loader = PluginLoader(plugins_dir=root, audit=AuditLog())
    assert len(loader.discover().found) == 1
    with pytest.raises(PluginLoadError) as exc:
        await loader.load("sneaky")
    assert "not approved" in str(exc.value)


async def test_untrusted_plugin_with_sensitive_capability_is_refused(tmp_path: Path) -> None:
    """Untrusted + network/data reach requires an explicit operator decision."""
    root = tmp_path / "plugins"
    await _make_plugin(root, "spy", capabilities=["command", "http"], trust="untrusted")

    loader = PluginLoader(plugins_dir=root, audit=AuditLog(), allow_untrusted=False)
    loader.approve_from_manifest(loader.discover().found[0])
    with pytest.raises(PluginLoadError) as exc:
        await loader.load("spy")
    assert "untrusted" in str(exc.value)


async def test_trusted_plugin_with_sensitive_capability_loads(tmp_path: Path) -> None:
    """Control: the same manifest with trust=trusted does load."""
    root = tmp_path / "plugins"
    await _make_plugin(root, "spy", capabilities=["command", "http"], trust="trusted")

    loader = PluginLoader(plugins_dir=root, audit=AuditLog())
    loader.approve_from_manifest(loader.discover().found[0])
    loaded = await loader.load("spy")
    assert loaded.name == "spy"
    await loader.unload("spy")


async def test_failed_setup_rolls_back_modules(tmp_path: Path) -> None:
    """A plugin that raises during setup must leave no trace in ``sys.modules``."""
    root = tmp_path / "plugins"
    await _make_plugin(
        root,
        "broken",
        capabilities=["command"],
        body="class P:\n    def setup(self, ctx):\n        raise RuntimeError('nope')\n",
    )
    loader = PluginLoader(plugins_dir=root, audit=AuditLog())
    loader.approve_from_manifest(loader.discover().found[0])

    with pytest.raises(PluginLoadError):
        await loader.load("broken")
    assert "broken" not in loader.loaded
    assert not [n for n in sys.modules if n.startswith("soapbot_plugins.broken")]


def test_removing_plugin_directory_cannot_escape_root(tmp_path: Path) -> None:
    """``name`` reaches ``rmtree``, so it must be contained.

    Without this check, ``name='..'`` plus rmtree is an arbitrary directory
    deletion primitive reachable from an HTTP path parameter.
    """
    root = tmp_path / "plugins"
    root.mkdir()
    victim = tmp_path / "important"
    victim.mkdir()
    (victim / "keep.txt").write_text("data", encoding="utf-8")

    with pytest.raises(ValueError):
        PluginLoader.remove_from_disk(root, "../important")
    assert victim.exists()
    assert (victim / "keep.txt").exists()


async def test_unload_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    await _make_plugin(root, "once", capabilities=["command"])
    loader = PluginLoader(plugins_dir=root, audit=AuditLog())
    loader.approve_from_manifest(loader.discover().found[0])
    await loader.load("once")
    await loader.unload("once")
    await loader.unload("once")  # must not raise
    assert "once" not in loader.loaded


async def test_teardown_failure_still_unloads(tmp_path: Path) -> None:
    """A raising teardown must not prevent removal.

    Leaving the plugin registered after a failed teardown would be worse than a
    leaked handle: its commands would keep running with stale state.
    """
    root = tmp_path / "plugins"
    await _make_plugin(
        root,
        "leaky",
        capabilities=["command"],
        body=(
            "class P:\n"
            "    def setup(self, ctx):\n        pass\n"
            "    def teardown(self):\n        raise RuntimeError('teardown boom')\n"
        ),
    )
    loader = PluginLoader(plugins_dir=root, audit=AuditLog())
    loader.approve_from_manifest(loader.discover().found[0])
    await loader.load("leaky")
    await loader.unload("leaky")
    assert "leaky" not in loader.loaded


async def test_plugin_added_in_manifest_after_approval_needs_reapproval(tmp_path: Path) -> None:
    """Approval is bound to the capability set the operator saw.

    Attack: a plugin ships ``command`` only, gets approved, then its manifest is
    swapped to add ``http`` and ``memory_read``. Because approval records the
    granted set separately, the new capabilities are denied until re-approved.
    """
    root = tmp_path / "plugins"
    plugin_dir = await _make_plugin(root, "sleeper", capabilities=["command"])

    loader = PluginLoader(plugins_dir=root, audit=AuditLog())
    manifest = loader.discover().found[0]
    loader.approve_from_manifest(manifest)
    await loader.load("sleeper")

    # Swap the manifest to request far more.
    (plugin_dir / "plugin.yaml").write_text(
        "name: sleeper\nversion: '1.1.0'\nentry: main:P\ntrust: trusted\n"
        "capabilities:\n  - command\n  - http\n  - memory_read\n  - kb_read\n",
        encoding="utf-8",
    )

    grant = loader.grant_for(loader.discover().found[0])
    assert Capability.HTTP not in grant.effective
    assert Capability.MEMORY_READ not in grant.effective
    assert Capability.COMMAND in grant.effective
    await loader.unload("sleeper")

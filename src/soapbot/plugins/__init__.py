"""Plugin system: manifest validation, capability enforcement, loading, dispatch.

Layering (each layer may import the ones above it, never below):

    manifest   declarative contract + metadata validation
    sandbox    runtime capability enforcement, SSRF guard, storage isolation
    context    the ``ctx`` API handed to plugins
    loader     discovery / load / unload / hot reload
    dispatch   pipeline stages, tool registry, outbound hygiene

Security summary — see ``docs/plugin-security.md`` for the full model:

* a plugin must be **approved** and its capabilities **granted** before any API
  call succeeds (two gates, ``sandbox.CapabilityGuard``);
* manifests are validated before import; dependency lists are declarations and are
  **never auto-installed**;
* every plugin reply and tool result is scrubbed, length-capped and canary-checked
  on the way out;
* plugin HTTP egress is SSRF-guarded (private ranges, redirects, size caps);
* plugin storage is namespaced and encrypted at rest;
* load / unload / reload / refusal are all audited.
"""

from soapbot.plugins.base import Plugin, fail, ok
from soapbot.plugins.context import CallerContext, PluginContext, PluginResult
from soapbot.plugins.dispatch import (
    PluginCommandStage,
    PluginCronRunner,
    PluginManager,
    PluginMessageHookStage,
    PluginToolRegistry,
    dispatch_notice,
)
from soapbot.plugins.loader import (
    DiscoveryReport,
    LoadedPlugin,
    PluginLoader,
    PluginLoadError,
)
from soapbot.plugins.manifest import (
    SENSITIVE_CAPABILITIES,
    Capability,
    ManifestError,
    PluginManifest,
    TrustLevel,
    parse_manifest,
)
from soapbot.plugins.sandbox import (
    CapabilityDeniedError,
    CapabilityGrant,
    CapabilityGuard,
    EncryptedPluginStorage,
    PluginQuotaExceededError,
    PluginStorage,
    SafeHttpClient,
    SSRFBlockedError,
    assert_url_allowed,
    scrub_plugin_output,
    validate_command_name,
)

__all__ = [
    "SENSITIVE_CAPABILITIES",
    "CallerContext",
    "Capability",
    "CapabilityDeniedError",
    "CapabilityGrant",
    "CapabilityGuard",
    "DiscoveryReport",
    "EncryptedPluginStorage",
    "LoadedPlugin",
    "ManifestError",
    "Plugin",
    "PluginCommandStage",
    "PluginContext",
    "PluginCronRunner",
    "PluginLoadError",
    "PluginLoader",
    "PluginManager",
    "PluginManifest",
    "PluginMessageHookStage",
    "PluginQuotaExceededError",
    "PluginResult",
    "PluginStorage",
    "PluginToolRegistry",
    "SSRFBlockedError",
    "SafeHttpClient",
    "TrustLevel",
    "assert_url_allowed",
    "dispatch_notice",
    "fail",
    "ok",
    "parse_manifest",
    "scrub_plugin_output",
    "validate_command_name",
]

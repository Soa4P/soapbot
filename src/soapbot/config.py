"""Global settings for soapbot.

All runtime configuration is loaded from environment variables (prefix SOAPBOT_)
or the optional ``.env`` file. Secrets are never stored in plaintext on disk here;
provider API keys live in the encrypted database (see ``soapbot.security.crypto``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"

#: A ``list[str]`` that accepts the form humans write in ``.env`` and in a shell.
#:
#: ``NoDecode`` is what makes this possible: without it pydantic-settings tries
#: ``json.loads`` on the raw value first, and ``SOAPBOT_OWNER_IDS=123,456`` aborts
#: startup with ``SettingsError: error parsing value for field "owner_ids"`` — an
#: error that names neither the offending value nor the accepted syntax. Every list
#: setting in this file is documented as comma-separated, so the documented form
#: has to work; JSON is still accepted because a container manifest or a test may
#: prefer it.
IdList = Annotated[list[str], NoDecode]


def _split_list(value: Any) -> Any:
    """Parse ``a,b`` / ``a;b`` / ``["a","b"]`` into a list of non-empty strings."""
    if not isinstance(value, str):
        return value
    raw = value.strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"列表值看起来是 JSON 但无法解析：{exc}。可以直接写逗号分隔，例如 123,456"
            ) from exc
        if not isinstance(parsed, list):
            raise ValueError("JSON 列表值必须是数组")
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]


class Settings(BaseSettings):
    """Process-wide settings."""

    model_config = SettingsConfigDict(
        env_prefix="SOAPBOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- server ----
    host: str = "127.0.0.1"
    port: int = 6185
    """HTTP API port. Chosen to avoid clashing with Halo(8090)/common dev ports."""

    # ---- storage ----
    data_dir: Path = DEFAULT_DATA_DIR
    db_url: str = ""
    """Defaults to sqlite+aiosqlite:///{data_dir}/soapbot.db when empty."""

    config_dir: Path = PROJECT_ROOT / "config"
    """Where provider/adapter/persona files live.

    Separate from ``data_dir`` on purpose: ``data/`` is the writable volume, and
    configuration that the service can rewrite is configuration a compromised plugin
    can rewrite. Container deployments mount this read-only.
    """

    # ---- runtime ----
    enable_runtime: bool = True
    """Build and start the bot runtime (pipeline + adapters) inside the app lifespan.

    On by default: the whole point of ``soapbot start`` is to answer messages, and a
    flag that has to be discovered before the bot works is a footgun. Tests that only
    exercise HTTP routes turn it off, since a runtime there would open the database
    and any configured adapter for no benefit.
    """

    # ---- streaming ----
    stream_reply: bool = False
    """Deliver a reply sentence by sentence while the model is still producing it.

    Off by default. Turning it on changes what a group receives from one message to
    several, which is a visible behaviour change — an operator should choose it, not
    discover it. It also requires the adapter to declare ``PROGRESSIVE``; an adapter
    that cannot send twice degrades to the single-message path on its own.
    """

    stream_chunk_chars: int = 80
    """Character budget before a sentence is cut at the nearest comma/space."""

    stream_first_packet_deadline: float = 1.2
    """Seconds to wait for the first sentence before sending what has accumulated.

    Without it a slow model makes time-to-first-message equal to total latency, which
    removes the only reason to stream at all.
    """

    stream_send_interval: float = 0.35
    """Minimum seconds between two progressive messages to the same group."""

    scheduler_tick_seconds: float = 30.0
    """How often due plugin cron jobs and expired budget reservations are swept.

    Thirty seconds bounds the lateness of a ``* * * * *`` job without making an idle
    process wake up more than ~2900 times a day.
    """

    # ---- security ----
    master_key: str = ""
    """Fernet master key (base64). Empty means auto-generate into keyfile."""

    master_key_file: Path | None = None
    """Read the master key from this file instead of the environment.

    Preferred over ``master_key`` in any containerised deployment: an environment
    variable is visible to ``docker inspect``, ``/proc/<pid>/environ`` and crash
    dumps, whereas a mode-0400 file mounted from a secret store is not. The value is
    read and stripped on first use; a trailing newline from ``openssl rand -base64``
    would otherwise corrupt the key.
    """

    # ---- budget (Wave 5) ----
    # Off by default: a ledger nobody configured would register a /budget command
    # that reads as a working control while governing nothing.
    enable_budget: bool = False
    budget_currency: str = "CNY"
    """Single accounting currency. The ledger never converts between currencies."""
    budget_period: str = "month"
    """``day`` / ``week`` / ``month`` — the window the cap applies to."""
    budget_period_cap_minor: int = 50_000
    """Per-period cap in **minor units** (fen). ¥500.00 by default.

    Integer minor units, not floats: ``0.1 + 0.2 != 0.3``, and a quota ledger that
    drifts eventually approves one request too many.
    """
    budget_per_request_cap_minor: int = 10_000
    """Single-request cap in minor units (¥100.00)."""
    budget_request_ttl_seconds: float = 24 * 3600
    """How long an unanswered request holds its reservation before expiring."""

    # ---- Bilibili (Wave 9) ----
    # Off by default. The README's disclaimer is only honest if enabling this is a
    # deliberate operator decision: Bilibili's developer agreement prohibits automated
    # collection, and a feature that is on unless switched off would make every user
    # party to that by default.
    enable_bilibili: bool = False
    bilibili_tier: str = "l1"
    """``l1`` (unsigned public metadata) or ``l2`` (adds wbi signing).

    ``l3`` is rejected at construction: it needs a logged-in session cookie, and the
    project holds no Bilibili account.
    """
    bilibili_timeout_seconds: float = 10.0
    bilibili_min_interval_seconds: float = 1.0
    """Minimum gap between outbound calls, so a burst of commands is not a scrape."""
    bilibili_rate_per_minute: int = 12
    bilibili_max_comments: int = 8
    """How many hot comments to feed the impression prompt."""

    jwt_secret: str = ""
    jwt_ttl_hours: int = 72

    init_token: str = ""
    """One-time bootstrap token printed on first start. Empty means auto-generate."""

    # ---- authority (privilege lists) ----
    # These are the ONLY source of bot privileges. Nothing in a chat message may
    # add to them. Format: comma-separated QQ numbers.
    owner_ids: IdList = []
    """Operators. The only role allowed to approve spending and edit access control."""

    admin_ids: IdList = []
    """Bot administrators: knowledge base, memory management, config."""

    member_ids: IdList = []
    """Explicitly privileged chat participants (beyond guest)."""

    first_run_owner: str = ""
    """Convenience for single-operator installs: treated as an owner if set."""

    trust_protocol_roles: bool = False
    """Honour an owner/admin role *claimed by the protocol payload*.

    Off by default and it should stay off. The role field is attacker-influenced
    on any transport that is not authenticated end-to-end, so trusting it turns a
    single forged payload into a full privilege escalation.
    """

    allow_untrusted_plugins: bool = False
    """Allow plugins marked ``trust: untrusted`` to hold sensitive capabilities.

    A plugin with ``http`` / ``memory_read`` / ``kb_read`` / ``send`` / ``storage``
    runs inside this process with the bot's network position and credentials
    access. Keeping this off means such a plugin must be marked trusted (a
    deliberate human decision) before it can load. Turning it on is equivalent to
    "run code from anyone in-process" and should be temporary, for review only.
    """

    allow_unknown_private: bool = False
    """Allow private messages from users not on ``private_allowlist``.

    Off by default: an open DM is a free, unlogged path into persona, memory and
    RAG, and it is the easiest way to exfiltrate a group's data one message at a
    time without ever touching the group.

    This flag is the *only* switch for the "anyone may DM the bot" case. Before it
    was wired through, private chat was unreachable under every configuration:
    ``build_runtime`` accepted the argument and never used it, so the documented
    ``SOAPBOT_ALLOW_UNKNOWN_PRIVATE=true`` did nothing. An operator who had a
    working dev setup with DMs saw them stop working in production with no error —
    the worst kind of configuration bug, because the setting claimed to be applied.
    """

    private_allowlist: IdList = []
    """Users allowed to DM the bot, regardless of ``allow_unknown_private``.

    Empty means "nobody", not "anybody": private chat stays closed until an
    operator names specific people. This asymmetry with groups is deliberate. A
    group has to be joinable to be useful and its membership is externally
    controlled, whereas a DM is a direct, private line into persona + memory + RAG
    with no other participants to notice. The cheap default must therefore be the
    closed one.
    """

    group_allowlist: IdList = []
    """Groups the bot will answer in. Empty means "any group it is invited to"."""

    group_blacklist: IdList = []
    """Groups to refuse even if ``group_allowlist`` is empty or contains them."""

    user_blacklist: IdList = []
    """Users refused everywhere, before any other rule is consulted."""

    # ---- logging ----
    log_level: str = "INFO"
    log_json: bool = True
    log_ring_size: int = 2000

    # ---- behaviour ----
    default_timezone: str = "Asia/Shanghai"

    @field_validator(
        "owner_ids",
        "admin_ids",
        "member_ids",
        "private_allowlist",
        "group_allowlist",
        "group_blacklist",
        "user_blacklist",
        mode="before",
    )
    @classmethod
    def _parse_lists(cls, value: Any) -> Any:
        return _split_list(value)

    @property
    def resolved_db_url(self) -> str:
        if self.db_url:
            return self.db_url
        return f"sqlite+aiosqlite:///{(self.data_dir / 'soapbot.db').as_posix()}"

    @property
    def providers_file(self) -> Path:
        return self.config_dir / "providers.yaml"

    @property
    def adapters_file(self) -> Path:
        return self.config_dir / "adapters.yaml"

    def ensure_dirs(self) -> None:
        for sub in ("", "logs", "uploads", "plugins", "avatars"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)


settings = Settings()

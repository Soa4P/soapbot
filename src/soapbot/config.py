"""Global settings for soapbot.

All runtime configuration is loaded from environment variables (prefix SOAPBOT_)
or the optional ``.env`` file. Secrets are never stored in plaintext on disk here;
provider API keys live in the encrypted database (see ``soapbot.security.crypto``).
"""

from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
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

    #: ``SOAPBOT_ENV_FILE`` relocates the ``.env`` this process reads. It exists so the
    #: settings page can write to the *same* file the process will read on next boot:
    #: a service started by systemd or a container does not have the repository as its
    #: working directory, so a hard-coded relative ``.env`` would make the panel save
    #: into a file nobody reads. Resolved once at import, which is the same lifetime as
    #: the config itself.
    model_config = SettingsConfigDict(
        env_prefix="SOAPBOT_",
        env_file=os.environ.get("SOAPBOT_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        # ``ignore`` at the pydantic level, with a targeted check on top (see
        # ``_reject_unknown_soapbot_keys``). ``forbid`` here looked right and was not:
        # a shared ``.env`` legitimately carries keys for other tools, and this project's
        # own file contains ``DEEPSEEK_API_KEY``. Forbidding extras turned a working
        # install into an ImportError on the first line of ``conftest`` — the failure
        # named a key the operator never meant for us.
        #
        # The typo this was meant to catch (``SOAPBOT_OWNER_ID`` for ``..._IDS``) is
        # still caught, and only for our own prefix, which is the actual blast radius.
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

    config_dir: Path = DEFAULT_DATA_DIR / "config"
    """Where the *runtime* provider/adapter/mcp files live. Writable.

    The settings page writes here, so it has to be writable. That is why it sits on the
    data volume rather than in the source tree: a rewritten ``providers.yaml`` in the
    image would be lost on the next container, and a read-only mount makes the panel's
    editor decorative — it can render a form and never save it.

    The shipped defaults live in :attr:`config_template_dir` and are copied here once,
    on first start. Copies, not symlinks: a container rebuild must not silently change
    the meaning of a file an operator has since edited.
    """

    napcat_home: Path | None = None
    """Where a hand-installed NapCat lives (Windows: the folder holding ``napcat.bat``).

    Only used to find that install's own ``webui.json`` so the panel can show its login QR.
    The container path the panel starts itself needs no setting.
    """

    napcat_webui_token: SecretStr = SecretStr("")
    """NapCat WebUI token, if it was set by hand or lives somewhere unusual.

    Takes precedence over discovery, because guessing a path is fine until it is not — and
    the failure ("no QR") looks identical either way.

    ``SecretStr``: this token authorises the WebUI that controls the QQ account, so it is
    a credential in every sense, not a display string.
    """

    napcat_ws_port: int = 3001
    """Port the protocol end listens on. The panel binds this when it starts the container
    itself, and connects to it when someone else started NapCat."""

    config_template_dir: Path = PROJECT_ROOT / "config"
    """Read-only defaults shipped with the code. Seeded into :attr:`config_dir`."""

    @model_validator(mode="after")
    def _config_follows_data(self) -> Settings:
        """Where the data went, the config went.

        Two real failures come from leaving these independent. The shipped ``.env``
        template sets ``SOAPBOT_CONFIG_DIR=./config``, which resolves against the process
        working directory — under systemd that is the checkout, so the panel edited the
        *template* and the next ``git pull`` reverted every provider it had been given.
        And an operator who points ``data_dir`` at a volume still gets a config directory
        next to the source tree unless they also know to move this one.

        So: a config path that was never moved (still the shipped default, or the template's
        relative ``./config``) follows the data directory instead.
        """
        if self.config_dir == Path("config") or self.config_dir == DEFAULT_DATA_DIR / "config":
            self.config_dir = self.data_dir / "config"
        return self

    # ---- runtime ----
    enable_runtime: bool = True
    """Build and start the bot runtime (pipeline + adapters) inside the app lifespan.

    On by default: the whole point of ``soapbot start`` is to answer messages, and a
    flag that has to be discovered before the bot works is a footgun. Tests that only
    exercise HTTP routes turn it off, since a runtime there would open the database
    and any configured adapter for no benefit.
    """

    # ---- latency ----
    history_turns: int = 16
    """How many archived messages are replayed into the prompt.

    Lowered from 40 after measuring: a long window pushed the transcript past the token
    budget, so the compressor folded history — a second model call — before the reply
    could start. Sixteen turns plus the rolling summary keeps the referents that matter
    and takes a network round trip off the hot path.
    """

    breaker_threshold: int = 3
    """Consecutive *total* failures before the router stops trying.

    Not 1, and the reason is concrete: "this stream produced no content" is a single
    provider misbehaving, and the caller's next move is to fall back to a normal call —
    which a breaker opened on the first failure would block. Three matches the
    per-provider cooldown threshold, so one bad turn still gets its failover.
    """

    breaker_base_seconds: float = 15.0
    """First pause after every provider fails in a row.

    Per-provider cooldown stops us hammering one dead endpoint. It does not cover the case
    where all of them are dead at once — a network partition, a revoked key shared across
    configs — where every message otherwise walks the whole list, pays each timeout, and
    still has nothing to say. The pause grows from here.
    """

    breaker_max_seconds: float = 300.0
    """Cap on the pause. Long enough to stop a retry storm, short enough that recovery does
    not need an operator."""

    # ---- outbound HTTP ----

    outbound_connect_timeout: float = 5.0
    """Seconds allowed to establish a connection, separately from reading a reply.

    Separate because the two failures mean different things. A refused or blackholed
    connect means the endpoint is down and the next provider should be tried now; a slow
    read means the model is thinking and the caller's own budget should decide. With a
    single flat timeout, a dead host costs the full completion budget before failover —
    five seconds instead of sixty turns a stalled conversation into a quick retry.
    """

    outbound_read_timeout: float = 60.0
    """Default seconds allowed between bytes once the request is sent.

    Providers override this with their own ``timeout`` from ``providers.yaml``; this is
    the value used by callers that have no per-provider budget (probes, webhooks).
    """

    outbound_write_timeout: float = 10.0
    """Seconds allowed to send the request body. A prompt large enough to stall writes is
    a prompt worth failing fast on."""

    outbound_pool_timeout: float = 5.0
    """Seconds to wait for a free connection when the pool is saturated.

    Short on purpose: queueing behind a full pool for a minute is indistinguishable from
    a hang, and the caller has other providers to try.
    """

    outbound_max_connections: int = 32
    """Ceiling on simultaneous sockets to *all* hosts.

    A busy group can produce a burst of concurrent replies, and without a ceiling each
    one opens its own connection — a spike that looks like an attack from the far side
    and that the local machine pays for in file descriptors.
    """

    outbound_max_keepalive: int = 16
    """Idle connections kept for reuse. Half the ceiling: enough to absorb the gap
    between two messages in the same conversation, few enough that idle sockets do not
    hold the pool against a burst."""

    outbound_keepalive_expiry: float = 30.0
    """Seconds an idle connection is kept.

    Longer than a typical gap between messages in one conversation, so the second
    message reuses the first one's TLS session instead of paying for a new handshake.
    """

    outbound_max_redirects: int = 3
    """Hops allowed when a caller opts into following redirects.

    Bounded because the alternative — ``follow_redirects=True`` — lets the server decide
    how many round trips the client makes, and never re-checks the destination. Each hop
    here goes back through the caller's validator.
    """

    outbound_user_agent: str = "soapbot/0.1 (+https://github.com/soapbot/soapbot)"
    """Sent on every outbound request.

    Set explicitly because httpx's default identifies the library, not the deployment,
    which makes this bot's traffic indistinguishable from any other httpx client in a
    provider's abuse dashboard.
    """

    model_error_notice: str = "我这会儿连不上模型，稍后再试。"
    """What the user sees when every provider is unavailable.

    Said out loud rather than staying silent: a bot that goes quiet during an outage is
    indistinguishable from a bot that is broken, and the operator's only signal becomes a
    user complaining in the group.
    """

    user_quota_calls: int = 30
    """How many model-backed turns one user may take per window.

    The limiters that already existed count *refusals* — a burst of denials means
    enumeration, which is a different question from cost. Nothing bounded a user who
    simply talks a lot: every message is a provider call, so one enthusiastic member can
    spend the operator's budget without ever being refused anything.

    Thirty per five minutes is roughly one turn every ten seconds, which is faster than a
    person types and slow enough that a normal conversation never notices. Privileged
    users are exempt — an operator debugging the bot should not be throttled by the
    control they are operating.
    """

    user_quota_window_seconds: float = 300.0
    """Window for :attr:`user_quota_calls`, in seconds. Sliding, not fixed: a fixed window
    lets a caller spend the full budget at 00:59 and again at 00:01."""

    user_quota_notice: str = "你说得有点快，我缓一下，稍后再聊。"
    """What the user sees when the quota is spent.

    Spoken rather than silent. Silence is correct for unauthorised traffic (it confirms
    the bot is listening), but a legitimate user hitting a rate limit needs to know why
    the bot stopped answering, or they conclude it broke.
    """

    max_embedding_chars: int = 2000
    """Longest text sent to the embedding provider, in characters.

    Providers bill by token and differ in what they do past their context limit — some
    truncate, some error, some return a vector of another dimension. Truncating here makes
    the behaviour ours and identical across providers. Applied to the query as well, so a
    stored vector and a query vector stay comparable.
    """

    max_recall_items: int = 20
    """Hard ceiling on recalled items per turn, whatever the caller asks for.

    Every recalled item costs prompt tokens on *every later turn*, so this is the number
    that bounds the cost of a busy or poisoned scope. Enforced in ``MemoryStore.recall``
    rather than at the call sites, because a limit honoured by some callers is not a
    limit.
    """

    max_prompt_tokens: int = 6000
    """Hard ceiling for the prompt. Raised only if the provider's context allows it."""

    # ---- streaming ----
    stream_reply: bool = True
    """Deliver a reply sentence by sentence while the model is still producing it.

    On by default because the alternative is the operator waiting for the *whole* reply
    before the first word appears, which is what "太慢" actually measures. It changes
    what a group receives from one message to several, so an adapter that cannot send
    twice degrades to the single-message path on its own; a deployment that wants one
    message sets ``SOAPBOT_STREAM_REPLY=false``.
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

    # ---- dispatch backpressure ----
    max_inflight_handlers: int = 32
    """Ceiling on message-handling tasks running at once, per adapter.

    Over the cap a new message is dropped instead of queued. A queue would be worse
    than the drop in both directions: every later reply would inherit the backlog's
    delay, and each waiting message still costs a task plus a full pipeline run once
    it drains. The number is deliberately well above real chat concurrency — one busy
    group produces a handful of overlapping turns — because the cost of hitting this
    limit is a dropped answer, and the cost of setting it too low is dropped answers
    during exactly the burst the operator cared about.

    ``SOAPBOT_MAX_INFLIGHT_HANDLERS=0`` disables the cap (old behaviour).
    """

    handler_timeout_seconds: float = 60.0
    """Wall-clock bound on one message's handling, measured from task start.

    Not a per-``await`` timeout: the model provider already bounds its own calls, and
    scattering deadlines across a dozen awaits makes the one number an operator cares
    about ("how long until this message is abandoned") impossible to find. Sixty
    seconds sits just above a worst-case model call plus one retry, so a timeout here
    means genuinely stuck rather than merely slow.

    ``0`` disables it.
    """

    # ---- plugin process ceiling ----
    max_plugin_workers: Annotated[int, Field(ge=1, le=64)] = 16
    """Maximum number of resident plugin worker processes at once.

    One plugin gets one worker. Without a ceiling, the number of processes is simply
    the number of entries an operator (or an attacker who can write to
    ``data/plugins``) puts in that directory; each one costs memory, a pipe pair and
    a potential crash loop. ``pids_limit`` in the container is a last resort, not a
    policy — by the time it fires the host is already degraded.

    Unlike ``max_inflight_handlers``, ``0`` is deliberately **invalid**: this is a
    security boundary, and an accidental "unlimited" must fail at startup rather than
    silently disable the cap. The upper bound matches
    ``soapbot.plugins.supervisor.MAX_PLUGIN_WORKERS``; the supervisor validates it
    again at construction so a direct builder call cannot exceed it either.
    """

    busy_notice: str = "忙不过来啦，稍后再试一次"
    """Reply sent when an @mention is dropped by the cap.

    Silence is not an acceptable answer to a direct mention: from the member's side an
    ignored "@" and a crashed bot look identical. Ordinary group chatter is dropped
    quietly — answering every dropped line would turn one overload into a flood of
    busy notices. Set to an empty string to drop mentions silently too.
    """

    voice_enabled: bool = False
    """Transcribe inbound voice messages into the conversation.

    Off by default because transcription costs a provider call per voice note and
    because it turns audio the bot was not listening to into text it will act on.
    """

    voice_tts_enabled: bool = False
    """Deliver replies as voice messages when the adapter can carry them.

    Requires the optional dependency: ``pip install 'soapbot[voice]'``. Missing it is
    not an error — replies go out as text and the reason is logged.
    """

    voice_tts_voice: str = "zh-CN-XiaoxiaoNeural"
    """Vendor voice name. Kept as a string because the set changes per provider."""

    voice_max_bytes: int = 8 * 1024 * 1024
    """Cap on downloaded audio. Applied while reading, not after."""

    voice_language: str = "zh"
    """Hint for the transcriber; providers may ignore it."""

    voice_allow_hosts: str = ""
    """Comma-separated hosts exempt from the public-address rule for audio downloads.

    Needed when the media endpoint is on the bot's own network: NapCat serves record
    files from its HTTP port, so a same-machine deployment hands over
    ``http://127.0.0.1:3000/...`` and the strict rule would refuse every voice
    message. Empty by default — naming a host is the operator's explicit decision to
    trust one internal address, and it stays visible in ``.env``.
    """

    default_locale: str = "zh-CN"
    """Language for text the bot sends into a chat: refusals, tool notes, voice labels.

    Deliberately *not* also the panel language — the panel picks its own language per
    browser (see ``webui/src/i18n``), because the person reading the console and the
    person reading the group are often not the same person. A persona card may
    override this per group, which is why the value travels on the pipeline context
    rather than being read from settings at the point of use.
    """

    scheduler_tick_seconds: float = 30.0
    """How often due plugin cron jobs and expired budget reservations are swept.

    Thirty seconds bounds the lateness of a ``* * * * *`` job without making an idle
    process wake up more than ~2900 times a day.
    """

    # ---- security ----
    master_key: SecretStr = SecretStr("")
    """Fernet master key (base64). Empty means auto-generate into keyfile.

    ``SecretStr`` rather than ``str`` so the value cannot leak by accident. A plain
    string shows up in ``repr(settings)``, in a traceback's local variables, and in any
    ``logger.debug("%s", settings)`` someone adds while debugging — and this particular
    string decrypts every provider API key in the database. Call sites use
    ``.get_secret_value()``, which is a deliberate, greppable act.
    """

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
    budget_period: Literal["day", "week", "month"] = "month"
    """The window the cap applies to.

    ``Literal`` rather than ``str`` so a typo is rejected at startup with the accepted
    values in the message. As a plain string, ``SOAPBOT_BUDGET_PERIOD=weekly`` was
    accepted and then silently matched no branch in the ledger, which is a spend cap
    that governs nothing.
    """
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
    bilibili_tier: Literal["l1", "l2"] = "l1"
    """``l1`` (unsigned public metadata) or ``l2`` (adds wbi signing).

    ``l3`` is not in the type at all: it needs a logged-in session cookie, and the
    project holds no Bilibili account. Encoding that in the type means the rejection
    happens while the settings are parsed, with the accepted values named, instead of
    surfacing later as an authentication failure against Bilibili.
    """
    bilibili_timeout_seconds: float = 10.0
    bilibili_min_interval_seconds: float = 1.0
    """Minimum gap between outbound calls, so a burst of commands is not a scrape."""
    bilibili_rate_per_minute: int = 12
    bilibili_max_comments: int = 8
    """How many hot comments to feed the impression prompt."""

    jwt_secret: SecretStr = SecretStr("")
    """Signing key for admin tokens.

    ``SecretStr`` for the same reason as :attr:`master_key`, and one more: this is the
    value that mints an ``owner`` session. A leaked log line here is a leaked login.
    """
    jwt_ttl_hours: int = 72

    init_token: SecretStr = SecretStr("")
    """One-time bootstrap token. Empty means persist one in ``<data>/init_token.txt``
    on first start and reuse it across restarts until it is redeemed.

    ``SecretStr`` because this string *is* the first login: whoever reads it becomes
    owner. It is compared against a submitted value, so the only legitimate consumer is
    a constant-time comparison, not a format string.
    """

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

    plugin_integrity_mode: Literal["block", "warn", "off"] = "block"
    """What to do when a plugin's code changed after it was approved.

    ``block`` (default) refuses to load it: approval was a decision about code the
    operator reviewed, and code that has since changed is code nobody approved. The
    refusal is audited and names both digests, so an operator can see *that* something
    changed before deciding to re-approve.

    ``warn`` loads it anyway and records the same audit entry. Useful while rolling out
    an upgrade across several plugins, when re-approving every one up front is
    impractical. It is a deliberate downgrade, not a safe default: the changed code runs.

    ``off`` skips the check. Kept because a deployment may manage plugins out of band
    and a check that cannot be turned off gets worked around by disabling the loader
    instead.

    An approval recorded before content digests existed has no value to compare against;
    that is reported as ``unknown`` and never blocked, in either mode.
    """

    plugin_index_url: str = ""
    """Community plugin index, fetched read-only for *discovery* only.

    Empty means "no index": the panel shows installed plugins and nothing else. Setting
    it does **not** make anything installable — the index lists versions and digests, and
    installation still goes through the local upload → approve → load path. Treating a
    remote list as a trust source would move the approval decision to whoever controls
    the JSON file, which is exactly the decision this project keeps local.
    """

    plugin_index_timeout_seconds: Annotated[float, Field(ge=0.5, le=15.0)] = 5.0
    """Hard ceiling on one index fetch.

    Short because this runs while an operator is waiting for the plugin page. A slow
    index is a broken index; the page renders "cannot discover" and stays usable.
    """

    plugin_index_ttl_seconds: Annotated[int, Field(ge=60, le=86400)] = 900
    """How long a fetched index is reused. Fifteen minutes: long enough that opening the
    page repeatedly does not hammer someone else's server, short enough that a revoked
    version shows up in the same session."""

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
    """Deprecated alias for ``reply_groups``.

    Kept so an existing ``.env`` keeps working after the upgrade. When both are set,
    ``reply_groups`` wins; ``build_access_policy`` logs once when it falls back.
    """

    reply_groups: IdList = []
    """Groups the bot replies in. Empty means every group it is invited to.

    Separately configurable from ``memory_collect_groups`` so an operator can have the
    bot learn in one set of groups while only speaking in another.
    """

    memory_collect_groups: IdList = []
    """Groups whose messages are archived into memory. Empty means every group.

    Archiving used to happen only after the wake check, so an un-mentioned message was
    never stored. That made "remember this group" impossible to configure: the bot only
    remembered what it was asked about. This list decouples the two.
    """

    group_personas: str = ""
    """Per-group persona cards, ``群号:人格ID`` pairs separated by commas.

    ``PersonaStore.bind_group`` existed but nothing loaded or saved it, so a binding
    made at runtime vanished on the next restart and there was no way to set one from
    the panel. Keeping it in ``.env`` reuses the write path the authority lists already
    use, including the "restart to apply" contract.
    """

    group_blacklist: IdList = []
    """Groups to refuse even if ``group_allowlist`` is empty or contains them."""

    user_blacklist: IdList = []
    """Users refused everywhere, before any other rule is consulted."""

    # ---- logging ----
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    """``Literal`` because ``logging_setup`` calls ``.upper()`` on it and hands the result
    to ``setLevel``. A typo there raises ``ValueError: Unknown level`` at import time —
    a bare traceback from inside the logging module, naming neither the setting nor the
    file it came from. Rejecting it here names the field and the accepted values."""
    log_json: bool = True
    log_ring_size: int = 2000
    slow_call_ms: int = 3000
    """A provider call slower than this is logged at WARNING. Below it the latency is
    DEBUG, not INFO: one line per successful model call turned the log ring into a
    list of numbers nobody reads, while the one slow call worth investigating had
    the same visual weight as the other five thousand."""

    # ---- request / auth boundary ----
    strict_loopback_auth: bool = True
    """When true, a loopback client needs a credential for any mutating request.
    Reads stay open so ``http://127.0.0.1:6185`` still renders before login. Turning
    this off restores the old "loopback is trusted for everything" behaviour; only
    the test suite does that, so its business assertions do not each have to become
    a login script. The strict path itself is pinned by tests/test_auth_cookie.py."""
    cookie_secure: bool = False
    """Set true behind an HTTPS reverse proxy. Over plain loopback HTTP a Secure
    cookie is never sent back, which would make login look like a no-op."""
    strict_startup: bool = True
    """Abort startup when an enabled adapter cannot be constructed. Failing at boot
    is the default: an adapter that only looks configured would otherwise surface
    hours later as a silently missing connection. Set false for a panel-only install
    that must come up even when an optional adapter is broken."""
    max_regex_input_chars: int = 20_000
    """Ceiling applied before any pattern runs over operator- or user-supplied text.
    The stdlib ``re`` has no timeout argument; bounding the input is the enforceable
    substitute without adding a dependency (``check_deps.py`` pins the runtime list)."""

    max_incoming_chars: int = Field(default=8_000, ge=200, le=100_000)
    """Total plain-text ceiling for one inbound message, measured after rendering.

    Every stage downstream — injection screening, recall, the prompt builder — costs
    time proportional to this. Without a ceiling, one member pasting a 5 MB log file
    makes every later stage in the pipeline pay for it, and the group's other messages
    queue behind that turn. Truncation is deliberate rather than rejection: a long
    message is usually a real message with a long tail, and dropping it entirely would
    look like the bot ignoring people.
    """
    max_segments: int = Field(default=64, ge=1, le=512)
    """Segment-count ceiling. OneBot lets a client send an unbounded array, and each
    segment is a dict that gets walked several times (render, screen, persist)."""
    max_segment_chars: int = Field(default=4_000, ge=100, le=50_000)
    """Per-segment ceiling, so one giant text segment cannot hide behind a small
    segment count."""
    max_json_depth: int = Field(default=32, ge=4, le=256)
    """Nesting ceiling checked before ``json.loads`` on untrusted frames.

    ``json`` itself recurses, and a payload like ``[[[[...]]]]`` a few thousand deep
    raises ``RecursionError`` from inside the C parser — which is not catchable as a
    ``JSONDecodeError`` and takes down whatever coroutine was decoding. Counting
    brackets first is a single linear pass and turns that into an ordinary rejection
    with a message naming the limit and the actual depth.
    """

    persona_growth_enabled: bool = True
    """Let the model rewrite a persona card without a review step.

    On by default because that is the chosen behaviour. The compensation lives in
    ``ai/persona_growth.py``: every write is a restorable version, only prose fields
    are writable, and each card has an hourly budget."""
    persona_growth_max_chars: int = Field(default=2000, ge=200, le=20000)
    """Rendered-card ceiling for a growth write. A prompt that outgrows this is
    usually a model dumping context, not a persona that got more specific."""
    persona_growth_per_hour: int = Field(default=6, ge=1, le=60)
    """How many growth writes one card may receive per hour. Bounds a loop that
    would otherwise rewrite the card on every message."""

    self_notes_limit: int = Field(default=40, ge=1, le=200)
    """How many L4 self-notes are kept. The oldest is evicted, not the newest:
    a note that survived many turns is more likely to describe a real pattern."""
    compaction_idle_minutes: int = Field(default=30, ge=0, le=1440)
    """Quiet time before a session is eligible for compaction. ``0`` disables it."""
    compaction_token_threshold: int = Field(default=6000, ge=0, le=200_000)
    """Context size that makes compaction worth a second model call. ``0`` disables."""
    timeline_window: int = Field(default=10, ge=1, le=50)
    """How many recent timeline events are shown to the model."""

    shutdown_grace_seconds: int = Field(default=10, ge=1, le=120)
    """How long shutdown may take before the process exits anyway.

    Without a bound, one adapter stuck in a read loop keeps the process alive until
    the supervisor escalates to SIGKILL, which looks like a hang on every restart.
    """

    # ---- behaviour ----
    default_timezone: str = "Asia/Shanghai"

    @field_validator(
        "owner_ids",
        "admin_ids",
        "member_ids",
        "private_allowlist",
        "group_allowlist",
        "reply_groups",
        "memory_collect_groups",
        "group_blacklist",
        "user_blacklist",
        mode="before",
    )
    @classmethod
    def _parse_lists(cls, value: Any) -> Any:
        return _split_list(value)

    @field_validator("plugin_integrity_mode", mode="before")
    @classmethod
    def _normalise_integrity_mode(cls, value: Any) -> Any:
        """Lower-case and strip before the ``Literal`` check runs.

        The rejection itself is the type's job now (``Literal["block", "warn", "off"]``),
        which is why the accepted values appear in the error without being restated here.
        What the type cannot do is accept ``BLOCK`` or `` block ``, and an operator who
        writes either means the same thing — so normalisation stays, validation does not.

        The failure mode this guards is worth keeping in view: a security switch that
        silently falls back to its default is worse than one that crashes, because
        "it looked like it worked" is indistinguishable from "it worked".
        """
        return str(value or "").strip().lower()

    @model_validator(mode="after")
    def _reject_unknown_soapbot_keys(self) -> Settings:
        """Fail on a misspelled ``SOAPBOT_*`` key, ignore everything else.

        ``extra="ignore"`` is right for a shared ``.env`` — other tools' keys are none of
        our business — but it also swallows our own typos. ``SOAPBOT_OWNER_ID`` (singular)
        used to start the process with an empty authority list, and the operator's only
        symptom was "the bot ignores me"; nothing in the logs named the mistake.

        So the check is scoped to the prefix we own. Keys without it are left alone, and
        the error names the offending key and the closest real field, because "did you
        mean" is the difference between a five-second fix and an hour of reading source.
        """
        known = {name.upper() for name in type(self).model_fields}
        prefix = "SOAPBOT_"
        # ``SOAPBOT_ENV_FILE`` is read by ``model_config`` above to decide *which* file to
        # load. It is a bootstrap variable for the settings machinery, not a setting, so it
        # is legitimately absent from ``model_fields`` and must not be reported as a typo.
        unknown = sorted(
            key
            for key in os.environ
            if key.startswith(prefix)
            and key[len(prefix) :] not in known
            and key[len(prefix) :] not in _BOOTSTRAP_KEYS
        )
        if not unknown:
            return self

        hints = []
        for key in unknown:
            stem = key[len(prefix) :]
            close = difflib.get_close_matches(stem, known, n=1, cutoff=0.7)
            hints.append(
                f"{key} (did you mean SOAPBOT_{close[0]}?)" if close else key
            )
        raise ValueError(
            "unknown SOAPBOT_ setting(s): "
            + ", ".join(hints)
            + ". Remove them, or fix the spelling — a setting that is silently ignored "
            "is worse than one that is rejected, because the process starts and looks "
            "healthy while the value you set does nothing."
        )

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

    @property
    def mcp_file(self) -> Path:
        """External tool servers. A property, not a constant, because the tests point
        ``config_dir`` at a temporary directory and a hard-coded path would keep writing
        to the checkout."""
        return self.config_dir / "mcp.yaml"

    def ensure_dirs(self) -> None:
        for sub in ("", "logs", "uploads", "plugins", "avatars"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)


#: Keys that are machinery rather than settings, so their absence from ``model_fields``
#: is correct. Shared by the validator and the file audit so the two cannot disagree.
_BOOTSTRAP_KEYS = frozenset({"ENV_FILE"})


def unknown_env_keys(path: Path) -> list[str]:
    """Misspelled ``SOAPBOT_*`` keys in an ``.env`` file, with a suggestion each.

    The validator above can only see ``os.environ``, and it deliberately does no IO — a
    validator that reads files runs on every construction, including in tests, and makes
    ``Settings()`` depend on the working directory. That left a real hole: a typo written
    into ``.env`` (the documented way to configure this) was loaded into the environment
    by ``load_dotenv_if_present`` *after* the settings object already existed, so nothing
    ever validated it and the operator saw the same silent "the setting does nothing".

    So the file is audited separately, at startup, where reading a file is expected.
    Returns human-readable findings rather than raising: a typo in a file the panel
    rewrites is worth a loud warning, not a process that refuses to boot.
    """
    if not path.is_file():
        return []
    known = {name.upper() for name in Settings.model_fields}
    prefix = "SOAPBOT_"
    findings: list[str] = []
    seen: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [f"无法读取 {path}：{exc}"]
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.partition("=")[0].strip()
        if not key.startswith(prefix) or key in seen:
            continue
        seen.add(key)
        stem = key[len(prefix) :]
        if stem in known or stem in _BOOTSTRAP_KEYS:
            continue
        close = difflib.get_close_matches(stem, known, n=1, cutoff=0.7)
        findings.append(f"{key} (did you mean SOAPBOT_{close[0]}?)" if close else key)
    return findings


settings = Settings()

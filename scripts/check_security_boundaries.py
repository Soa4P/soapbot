#!/usr/bin/env python
"""Offline audit of the 20 security / error / logging boundaries.

Why a gate like this exists
---------------------------
Most of these properties are negative: no ``shell=True``, no ``pickle.loads``, no
wildcard CORS, no raw exception text in a response, no bearer token in localStorage.
A unit test can prove one attack is refused today; it cannot prove that somebody did
not quietly reintroduce the primitive next month.

The script reads source only. It starts no server, no container, no network
connection, so it behaves the same on a laptop, in CI and before a release. Every
result prints the evidence it relied on. A missing invariant exits non-zero.

Each of the 20 contracts has a risk level, taken from the same grading used in the
review that produced them. Levels are informational: *every* missing invariant fails
the gate, including the low ones, because a low-risk regression that is allowed to
land becomes the baseline for the next one.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "soapbot"
API = SRC / "api"
WEBUI = ROOT / "webui" / "src"
DOCS = ROOT / "docs"
CI = ROOT / ".github" / "workflows" / "ci.yml"
MAKEFILE = ROOT / "Makefile"

AUTH = API / "auth.py"
ADMIN = API / "admin.py"
APP = SRC / "app.py"
CONFIG = SRC / "config.py"
ERRORS = API / "errors.py"
LOG_CONTEXT = SRC / "core" / "log_context.py"
LOGGING = SRC / "logging_setup.py"
AUDIT = SRC / "security" / "audit.py"
INJECTION = SRC / "security" / "injection.py"
INSTALLER = SRC / "plugins" / "installer.py"
ROUTER = SRC / "providers" / "router.py"
PIPELINE = SRC / "core" / "pipeline.py"
PLUGINS_API = API / "plugins.py"
BILIBILI_API = API / "bilibili.py"
SETTINGS_API = API / "settings.py"
CLIENT = WEBUI / "api" / "client.ts"
CONTRACT_DOC = DOCS / "security-boundaries.md"

#: Files whose contents are checked for forbidden primitives.
PY_FILES = sorted(SRC.rglob("*.py"))
API_FILES = sorted(API.glob("*.py"))
VUE_FILES = sorted(WEBUI.rglob("*.vue"))
PROVIDER_FILES = sorted((SRC / "providers").glob("*.py"))


@dataclass
class Result:
    code: str
    level: str
    ok: bool
    detail: str
    evidence: str = ""


def _text(path: Path) -> str:
    # utf-8-sig: several source files carry a BOM, and ast.parse() rejects it as
    # an "invalid non-printable character" — a silent skip of exactly the files
    # the AST-based checks were supposed to cover.
    return path.read_text(encoding="utf-8-sig") if path.exists() else ""


def _line_of(text: str, needle: str) -> str:
    for number, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return f"line {number}: {line.strip()[:110]}"
    return f"missing {needle!r}"


def _require(path: Path, needle: str, code: str, level: str, detail: str) -> Result:
    text = _text(path)
    return Result(code, level, needle in text, detail, f"{path.name} {_line_of(text, needle)}")


def _forbid(path: Path, needle: str, code: str, level: str, detail: str) -> Result:
    text = _text(path)
    return Result(
        code,
        level,
        needle not in text,
        detail,
        f"{path.name} {_line_of(text, needle) if needle in text else 'absent'}",
    )


def _forbid_in(paths: list[Path], needle: str, code: str, level: str, detail: str) -> Result:
    hits = [f"{p.relative_to(ROOT)}:{_line_of(_text(p), needle)}" for p in paths if needle in _text(p)]
    return Result(
        code, level, not hits, detail, "; ".join(hits) if hits else f"absent in {len(paths)} files"
    )


def _is_os_environ(node: ast.expr) -> bool:
    """Whether ``node`` evaluates to the host environment mapping."""
    if isinstance(node, ast.Attribute) and node.attr == "environ":
        return isinstance(node.value, ast.Name) and node.value.id == "os"
    if isinstance(node, ast.Call):
        # ``os.environ.copy()`` and ``dict(os.environ)`` are the same leak spelled
        # differently; catching only the literal unpacking invites the rewrite.
        if isinstance(node.func, ast.Attribute) and node.func.attr == "copy":
            return _is_os_environ(node.func.value)
        if isinstance(node.func, ast.Name) and node.func.id == "dict":
            return bool(node.args) and _is_os_environ(node.args[0])
    return False


def _forbid_host_env(code: str, level: str, detail: str) -> Result:
    """AST check: no third-party child is handed the host environment.

    Deliberately not a substring scan. ``core/proc_env.py`` documents the defect by
    quoting the line it replaced — ``{**os.environ, **server.env}`` — and a text gate
    reports that explanation as a live occurrence. The gate would then fail on the very
    file that fixes the bug, and the obvious way to make it green is to delete the
    explanation, which is the opposite of what the gate is for. The AST sees the
    unpacking; it does not see prose.
    """
    offenders: list[str] = []
    for path in PY_FILES:
        try:
            tree = ast.parse(_text(path))
        except SyntaxError:  # pragma: no cover - the lint gate owns syntax
            continue
        for node in ast.walk(tree):
            where = ""
            if isinstance(node, ast.Dict):
                # ``zip(..., strict=False)``: a dict display with a ``**`` key has a
                # ``None`` in ``keys`` and the same length in ``values``, but being
                # explicit here keeps the intent readable.
                if any(
                    key is None and _is_os_environ(value)
                    for key, value in zip(node.keys, node.values, strict=False)
                ):
                    where = "**os.environ"
            elif (
                isinstance(node, ast.keyword)
                and node.arg == "env"
                and _is_os_environ(node.value)
            ):
                where = "env=os.environ"
            if where:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} {where}")
    return Result(
        code, level, not offenders, detail,
        "; ".join(offenders) if offenders else f"absent in {len(PY_FILES)} files",
    )


#: The number of contracts the table must never fall below. A ratchet, not a target:
#: the count may grow, it may not shrink. Same logic as ``blocked_versions.json`` —
#: removing a contract is how a boundary quietly becomes a suggestion.
MIN_CONTRACTS = 20

#: Every prose location that states the contract count, with the needle shape that
#: location uses. ``{n}`` is substituted with the number derived from the table, so
#: this list never hard-codes a digit — the digit is an output of the gate, not an
#: input to it. That is the whole point: ten hand-written numbers are why they drifted.
COUNT_CLAIMS: tuple[tuple[Path, str], ...] = (
    # The H1 and the section heading are separate claims on purpose. A needle of
    # ``{n} 项防线契约`` alone matches the H1, so editing only the section heading
    # leaves it green — the test suite caught exactly that when this was one entry.
    (CONTRACT_DOC, "安全边界与错误日志：{n} 项防线契约"),
    (CONTRACT_DOC, "## {n} 项防线契约"),
    (DOCS / "guide.md", "{n} 项边界逐条证据"),
    (DOCS / "operations.md", "{n} 项安全与错误日志契约"),
    (DOCS / "reference-ecosystem.md", "{n} 项各有一条防线"),
    (DOCS / "reference-ecosystem.md", "{n} 项逐条证据见"),
    (DOCS / "security-model.md", "{n} 项契约、每条的判定与证据"),
    (DOCS / "verification-matrix.md", "{n} 项安全与错误日志契约"),
    (MAKEFILE, "{n} 项安全与错误日志边界审计"),
    (CI, "The {n} contracts in docs/security-boundaries.md"),
)


def _contract_rows(text: str) -> list[int]:
    """The ``#`` column of the contract table, in document order."""
    return [int(m) for m in re.findall(r"^\|\s*(\d{2})\s*\|", text, re.MULTILINE)]


def _contract_count_is_consistent(code: str, level: str, detail: str) -> Result:
    """The prose must agree with the table, and the table may not shrink.

    Three things, and all three are needed:

      1. the row numbers run 01..n with no gap and no repeat — this catches "delete
         row 12", which is how a contract disappears without anyone noticing;
      2. ``n >= MIN_CONTRACTS`` — a ratchet, so "delete a row *and* update the prose"
         is still a failure;
      3. every ``COUNT_CLAIMS`` location contains the needle built from the derived
         ``n`` — so the seven prose statements cannot drift from the table.

    The check this replaces was ``_require(CONTRACT_DOC, "## 20 项防线契约")``, which
    proves the characters exist but not that they are *right*: delete a table row and
    leave the heading alone and it stays green. A number written in ten places needs a
    gate that reads the number from one place.
    """
    text = _text(CONTRACT_DOC)
    rows = _contract_rows(text)
    if not rows:
        return Result(code, level, False, detail, f"{CONTRACT_DOC.name}: no contract rows found")

    n = len(rows)
    problems: list[str] = []

    expected = list(range(1, n + 1))
    if rows != expected:
        # Report the first divergence rather than the whole list: with 20 rows the
        # full diff is noise, and the first gap is the one that was deleted.
        for index, (got, want) in enumerate(zip(rows, expected, strict=False), 1):
            if got != want:
                problems.append(f"row {index} is {got:02d}, expected {want:02d}")
                break
        else:
            problems.append(f"{n} rows but numbering ends at {rows[-1]:02d}")

    if n < MIN_CONTRACTS:
        problems.append(f"{n} contracts, ratchet floor is {MIN_CONTRACTS}")

    missing: list[str] = []
    for path, template in COUNT_CLAIMS:
        needle = template.format(n=n)
        if needle not in _text(path):
            missing.append(f"{path.relative_to(ROOT)} lacks {needle!r}")
    problems.extend(missing)

    evidence = (
        "; ".join(problems)
        if problems
        else f"{n} contracts, rows 01-{n:02d} contiguous, {len(COUNT_CLAIMS)} prose claims agree"
    )
    return Result(code, level, not problems, detail, evidence)


def _no_silent_catch(code: str, level: str, detail: str) -> Result:
    """AST check: a swallowed exception must not be the whole handler body."""
    offenders: list[str] = []
    for path in PY_FILES:
        try:
            tree = ast.parse(_text(path))
        except SyntaxError:  # pragma: no cover - the lint gate owns syntax
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body = [n for n in node.body if not isinstance(n, ast.Expr) or not isinstance(n.value, ast.Constant)]
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return Result(
        code, level, not offenders, detail, "; ".join(offenders) if offenders else "no silent catch"
    )


def _only_safe_vhtml(code: str, level: str, detail: str) -> Result:
    """The single v-html use must stay bound to the locally generated QR SVG.

    Check the *attribute*, not any line containing the word: ProtocolEnd.vue has
    a comment explaining why the binding is safe, and a naive substring scan
    reports that comment as a second injection sink.
    """
    import re

    binding = re.compile(r'\bv-html\s*=\s*"([^"]+)"')
    hits: list[str] = []
    found = 0
    for path in VUE_FILES:
        for number, line in enumerate(_text(path).splitlines(), 1):
            match = binding.search(line)
            if match is None:
                continue
            found += 1
            if match.group(1).strip() != "qrSvg":
                hits.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:90]}")
    evidence = "; ".join(hits) if hits else f"{found} binding(s), all qrSvg"
    return Result(code, level, not hits and found > 0, detail, evidence)


def checks() -> list[Result]:
    out: list[Result] = []
    add = out.append

    # 01 — path construction
    add(_require(ADMIN, "_require_doc_id(", "s01", "high", "every doc_id endpoint uses the shared validator"))
    add(_forbid_in(API_FILES, "open(f\"{", "s01", "high", "no f-string path directly opened in an API handler"))

    # 02 — shell / command construction
    add(_forbid_in(PY_FILES, "shell=True", "s02", "critical", "no shell=True anywhere in the package"))
    add(_forbid_in(PY_FILES, "os.system(", "s02", "critical", "no os.system in the package"))
    add(_forbid_in(PY_FILES, "create_subprocess_shell", "s02", "critical", "no shell subprocess"))
    add(_require(SRC / "mcp" / "client.py", "create_subprocess_exec", "s02", "critical", "MCP argv stays a list"))

    # 03 — deserialisation
    add(_forbid_in(PY_FILES, "import pickle", "s03", "critical", "no pickle import"))
    add(_forbid_in(PY_FILES, "pickle.loads", "s03", "critical", "no pickle.loads"))
    add(_forbid_in(PY_FILES, "yaml.load(", "s03", "critical", "no unsafe yaml.load"))
    add(_require(SRC / "plugins" / "loader.py", "yaml.safe_load", "s03", "critical", "manifest uses safe_load"))

    # 04 — HTML injection
    add(_only_safe_vhtml("s04", "high", "v-html never binds remote or user content"))
    add(_require(APP, "Content-Security-Policy", "s04", "medium", "CSP response header is set"))

    # 05 — credential storage
    # Check the API call, not the word: the file header explains *why* web storage
    # is not used, and a substring gate would flag that explanation as a leak.
    add(_forbid(CLIENT, "localStorage.", "s05", "high", "no token in localStorage"))
    add(_forbid(CLIENT, "Authorization", "s05", "high", "no browser-injected bearer header"))
    add(_require(CLIENT, "credentials: 'include'", "s05", "high", "cookie is sent with same-origin requests"))
    add(_require(AUTH, "httponly=True", "s05", "critical", "session cookie is HttpOnly"))
    add(_require(AUTH, "samesite=", "s05", "high", "session cookie pins SameSite"))
    # refresh is a POST that rotates cookies without having a CSRF token yet; it
    # must go through authentication like any other state-changing route.
    add(_require(AUTH, "_auth: dict[str, Any] = Depends(require_api_auth)",
                 "s05", "critical", "refresh is authenticated before rotating the session"))
    add(_require(AUTH, "_reject_cross_site(request)", "s05", "high",
                 "login refuses a cross-site Origin"))

    # 06 — CORS
    add(_forbid(APP, 'allow_origins=["*"]', "s06", "critical", "no wildcard origin list"))
    add(_forbid(APP, "allow_origin_regex=", "s06", "critical", "no regex wildcard for origins"))
    add(_require(APP, "allow_origins=_CORS_ORIGINS", "s06", "critical", "CORS stays an explicit allowlist"))

    # 07 — log injection
    add(_forbid(LOGGING, '{"ts":"%(asctime)s"', "s07", "high", "no hand-built JSON log line"))
    add(_require(LOGGING, "json.dumps(", "s07", "high", "log fields are serialised, not concatenated"))
    add(_require(LOGGING, "_clean_text(", "s07", "high", "control characters are stripped before logging"))
    add(_require(LOGGING, "_clean_and_redact(", "s07", "high", "credential-shaped text is redacted at the log exit"))
    add(_require(LOGGING, "_PlainFormatter", "s07", "high", "human-readable mode also cleans tracebacks"))

    # 08 — bounded regex
    add(_require(INJECTION, "def bounded_scan(", "s08", "medium", "one bounded entry point for user-input regex"))
    add(_require(CONFIG, "max_regex_input_chars", "s08", "medium", "regex input ceiling is configurable"))

    # 09 — template rendering
    add(_forbid_in(PY_FILES, "from jinja2", "s09", "high", "no Jinja in the Python package"))
    add(_forbid_in(PY_FILES, "from_string(", "s09", "high", "no runtime template compilation"))

    # 10 — upload type
    add(_require(INSTALLER, "data.startswith(_ZIP_MAGIC)", "s10", "medium", "archive magic bytes are actually checked"))
    add(_require(INSTALLER, "suffix not in _ALLOWED_SUFFIXES", "s10", "medium", "entry suffix allowlist is enforced"))
    add(_require(INSTALLER, "flag_bits & 0x1", "s10", "medium", "encrypted entries are refused up front"))
    add(_require(INSTALLER, "archive mixes a root manifest with nested entries", "s10", "medium",
                 "a second tree cannot hide behind a root manifest"))
    add(_require(APP, "MAX_REQUEST_BODY_BYTES", "s10", "medium", "request body ceiling still in place"))

    # 11 — error response
    add(_require(ERRORS, "class AppError", "s11", "high", "one application error base class"))
    add(_require(ERRORS, "app.add_exception_handler(AppError, _app_error)", "s11", "high", "global exception handler registered"))
    add(_require(APP, "install_error_handlers(app)", "s11", "high", "handlers are installed at app construction"))
    # Only patterns that appear in an HTTPException response are listed here.
    # ``detail=f"{exc} from=..."`` in an audit record is a server-side event, not
    # a response, and banning the substring would flag the audit call instead.
    for needle in ("detail=str(exc)", 'detail=f"invalid value:'):
        add(_forbid_in(API_FILES, needle, "s11", "high", f"no raw exception text in a response ({needle})"))
    add(_forbid_in(API_FILES, "traceback.format_exc()", "s11", "critical", "no traceback in a response"))
    add(_require(ERRORS, 'origin.startswith("config_")', "s11", "high",
                 "variable-name reflection is limited to config parsing"))

    # 12 — sensitive endpoints
    add(_require(AUTH, "def require_role(", "s12", "critical", "role dependency factory exists"))
    for path, label in (
        (ADMIN, "admin"), (API / "pipeline.py", "metrics/traces"),
        (API / "security.py", "audit"), (PLUGINS_API, "plugin management"),
        (BILIBILI_API, "bilibili views"),
    ):
        add(_require(path, "require_role(", "s12", "critical", f"{label} routes declare a role"))
    add(_require(PLUGINS_API, "require_role(Role.ADMIN)", "s12", "critical",
                 "plugin install/load is ADMIN, not MEMBER"))
    add(_require(AUTH, "if settings.strict_loopback_auth and request.method in _MUTATING",
                 "s12", "critical", "loopback writes require a credential"))
    add(_require(AUTH, "_loopback_role()", "s12", "critical",
                 "loopback role is computed, not hardcoded owner"))
    add(_require(AUTH, "if not host:", "s12", "high", "opaque Origin is refused"))
    add(_require(SETTINGS_API, "safe_detail(", "s12", "high",
                 "settings endpoint no longer echoes validation errors"))
    # These two files compute their role floor inline rather than through the router
    # dependency. The s12 sweep above would not notice if either check disappeared.
    add(_require(SETTINGS_API, "_require_config_permission(", "s12", "high",
                 "settings writes keep their inline permission floor"))
    add(_require(AUTH, "Role.OWNER", "s12", "high",
                 "revoke-all keeps its inline OWNER floor"))

    # 13 — swallowed exceptions
    add(_no_silent_catch("s13", "medium", "no except block whose entire body is pass"))

    # 14 — PII in logs
    add(_forbid_in(PROVIDER_FILES, "resp.text[:", "s14", "high", "provider response bodies never enter last_error"))
    add(_require(ROUTER, "redact(scrub_prompt_echo", "s14", "high", "provider errors pass through both cleaners"))
    add(_require(AUDIT, "_redact_detail", "s14", "high", "audit detail keeps its redaction"))
    add(_require(LOGGING, "from soapbot.security.injection import redact", "s14", "high",
                 "log exit redacts credential-shaped text"))
    add(_forbid(ERRORS, "exc.detail[:300]", "s14", "high",
                "internal diagnosis is not echoed into the log ring message"))

    # 15 — trace id
    add(_require(LOG_CONTEXT, "ContextVar", "s15", "medium", "request-scoped context exists"))
    add(_require(APP, "X-Request-ID", "s15", "medium", "request id is returned to the caller"))
    add(_require(APP, "log_context.reset(tokens)", "s15", "medium", "context is reset on every response"))
    add(_require(PIPELINE, "log_context.bridge_trace_id", "s15", "medium",
                 "chat trace id is bridged into structured logs"))
    add(_require(LOGGING, "trace_id", "s15", "medium", "trace id is a structured log field"))

    # 16 — error layering
    add(_require(ERRORS, "STATUS_BY_KIND", "s16", "medium", "one error-kind to status mapping"))
    add(_require(ERRORS, "def install_error_handlers(", "s16", "medium", "handlers installed in one place"))

    # 17 — fail fast
    add(_require(CONFIG, "strict_startup: bool = True", "s17", "medium", "fail-fast is the production default"))
    add(_require(APP, 'raise RuntimeError(f"strict startup refused', "s17", "medium",
                 "startup actually aborts on the strict branch"))

    # 18 — level, slow calls, locating fields
    add(_require(CONFIG, "slow_call_ms", "s18", "low", "slow-call threshold is configurable"))
    add(_require(ROUTER, "slow_call_ms", "s18", "low", "provider latency is compared to a threshold"))
    add(_require(AUDIT, "message_id", "s18", "low", "audit events carry message_id"))
    add(_require(AUDIT, "provider", "s18", "low", "audit events carry provider"))

    # 19 — what a third-party child process may see
    # An MCP server is code the operator did not write, and `SECURITY.md` grades it
    # untrusted. Handing it the host environment contradicted that grade: it could read
    # the master key and every provider API key straight out of `os.environ`. The plugin
    # side already had an allowlist; the two now share one, so the lists cannot drift.
    add(_forbid_host_env("s19", "critical",
                         "no third-party child inherits the host environment"))
    add(_require(SRC / "mcp" / "client.py", "sanitize_env(", "s19", "critical",
                 "MCP child environment goes through the shared allowlist"))
    add(_require(SRC / "core" / "proc_env.py", "SAFE_ENV_KEYS", "s19", "critical",
                 "one allowlist defines what a third-party child may see"))

    # 20 — one invisible-character table
    # There were five copies and they had drifted: the injection screen knew about the
    # bidi overrides and the Unicode tag characters, the other three did not, and none
    # of them covered U+2066-U+2069. A character missing from the weakest copy passes
    # the injection screen, the memory vet and the tool-text scrubber at once, and then
    # reaches the prompt — where the model reads what the regex could not see.
    add(_require(SRC / "core" / "text.py", "0x2066", "s20", "critical",
                 "the shared table covers the Unicode isolate characters"))
    for rel in (
        "security/injection.py",
        "ai/stages.py",
        "core/stages.py",
        "security/principal.py",
    ):
        add(_require(SRC / rel, "from soapbot.core.text import INVISIBLE", "s20", "critical",
                     f"{rel} reads the shared invisible-character table"))

    # The AI reviewer is advisory by construction. Its verdict must never substitute
    # for a deterministic gate, and its own self-description must not quietly become
    # a claim that it decides anything. Pin the two sentences and the absence of any
    # AI verdict wiring in the backend jobs.
    add(_require(ROOT / "scripts" / "ai_review.py", "What this is *not*: a gate",
                 "wire", "high", "AI review states it is not a gate"))
    add(_require(ROOT / ".github" / "workflows" / "ai-review.yml",
                 "This job never approves and never merges",
                 "wire", "high", "AI review never approves or merges"))
    add(_forbid_in([CI], "AI_REVIEW_MODE", "wire", "high",
                   "the backend gates never consult the AI verdict"))

    # Wiring: the gate must run in CI and locally, or it decays into a script nobody calls.
    add(_require(CI, "scripts/check_security_boundaries.py", "wire", "medium", "CI runs this gate"))
    add(_require(MAKEFILE, "scripts/check_security_boundaries.py", "wire", "medium", "make check runs this gate"))
    add(_contract_count_is_consistent("wire", "low",
                                      "the prose contract count equals the table, and never shrinks"))
    return out


def main() -> int:
    # Same guard as the other scripts/*.py gates: a cp936 console would otherwise
    # die on the first Chinese evidence line, and a gate that crashes on its own
    # output is indistinguishable from a gate that failed.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    results = checks()
    for item in results:
        mark = "ok  " if item.ok else "FAIL"
        print(f"[{mark}] {item.code:<5} {item.level:<8} {item.detail}")
        print(f"       evidence: {item.evidence}")
    failed = [item for item in results if not item.ok]
    print(f"\nsecurity boundary audit: {len(results) - len(failed)}/{len(results)} invariants hold")
    if failed:
        print(f"{len(failed)} missing: {', '.join(sorted({i.code for i in failed}))}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

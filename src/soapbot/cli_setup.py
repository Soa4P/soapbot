"""``soapbot setup`` — the panel's configuration flow, for a server with no browser.

Why a command and not "just edit the YAML"
------------------------------------------
The panel exists so nobody edits YAML by hand, and that reasoning does not stop at the
edge of an SSH session. A headless Ubuntu box is *more* likely to be edited over SSH with
no review, no validation and no record — the exact situation ``core/config_write.py`` was
written to end. So this module does what the browser does, in the same order:

    read the current file -> merge the answers -> validate with the startup parser
    -> write atomically (only if it validates)

The two properties that matter, and both are tested:

* **A failing candidate is never written.** ``build_patch`` runs ``parse_providers`` /
  ``validate_adapters`` first, so a typo'd ``env:`` reference fails here instead of
  turning the next boot into a crash loop.
* **The key is never echoed.** Not in the prompt, not in the summary, not in an error.

Non-interactive flags exist for Ansible and image builds: when stdin is not a TTY the
prompts are skipped entirely, and missing required values are an error rather than a
hang. Two exits are worth distinguishing — 0 for success, 2 for "the answers were
insufficient", 1 for "the file was not written".
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from soapbot.config import settings
from soapbot.core import config_write
from soapbot.core.config_files import ConfigError

logger = logging.getLogger(__name__)

#: Exit codes. 2 is argparse's convention for "bad usage", which is exactly what a
#: missing ``--base-url`` in a non-interactive run is.
EXIT_OK = 0
EXIT_NOT_WRITTEN = 1
EXIT_BAD_INPUT = 2


# --------------------------------------------------------------------------- prompts
def _interactive() -> bool:
    """A TTY check that is safe under cron/Ansible/CI.

    ``sys.stdin`` can be missing entirely (``pythonw``, some supervisors), so this asks
    the object rather than trusting it to exist.
    """
    stdin = getattr(sys, "stdin", None)
    try:
        return bool(stdin is not None and stdin.isatty())
    except Exception:  # pragma: no cover - closed or exotic stdin
        return False


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default
    if answer:
        return answer
    return default


def _ask_choice(prompt: str, choices: tuple[str, ...], default: str) -> str:
    while True:
        answer = _ask(f"{prompt} ({'/'.join(choices)})", default).lower()
        if answer in choices:
            return answer
        print(f"  只能是 {'/'.join(choices)}", file=sys.stderr)


# ---------------------------------------------------------------------------- patches
def provider_patch(
    *,
    provider_id: str,
    base_url: str,
    model: str,
    api_key: str = "",
) -> list[dict[str, Any]]:
    """One provider entry, shaped for :func:`config_write.apply_provider_patch`.

    ``api_key`` empty means :data:`config_write.UNCHANGED`: re-running ``setup`` to fix a
    model name must not wipe a key the operator already stored — the same trap the panel's
    mask/``__UNCHANGED__`` pair exists for.
    """
    entry: dict[str, Any] = {
        "id": provider_id,
        "kind": "openai_compat",
        "base_url": base_url.rstrip("/"),
        "model": model,
        "api_key": api_key or config_write.UNCHANGED,
        "enabled": True,
    }
    return [entry]


def adapter_patch(
    *,
    kind: str,
    mode: str,
    account_id: str = "",
    ws_url: str = "",
    host: str = "",
    port: int | None = None,
    access_token: str = "",
) -> list[dict[str, Any]]:
    """One adapter entry. Only the keys the chosen mode uses are sent.

    A stale ``host`` left over from a previous reverse setup would give the file two
    connection targets with no way to tell which one wins — the same reasoning as the
    panel's ``payload()``.
    """
    entry: dict[str, Any] = {
        "kind": kind,
        "mode": mode,
        "enabled": True,
        "access_token": access_token or config_write.UNCHANGED,
    }
    if account_id:
        entry["account_id"] = account_id
    if mode == "reverse":
        entry["host"] = host or "127.0.0.1"
        entry["port"] = int(port or 6700)
    else:
        entry["ws_url"] = ws_url
    return [entry]


def _write(path: Path, patch: list[dict[str, Any]], *, adapters: bool) -> tuple[bool, str]:
    """Validate, then write. Returns ``(written, message)``.

    ``base_hash=""`` is intentional: this is the only editor, so there is no concurrent
    diff to conflict with. The operator's confirmation is the prompt they just answered.
    """
    try:
        result = config_write.build_patch(
            path=path,
            patch=patch,
            base_hash="",
            apply_fn=config_write.apply_adapter_patch if adapters else config_write.apply_provider_patch,
            validate_fn=config_write.validate_adapters if adapters else config_write.validate_providers,
            filename=path.name,
        )
    except ConfigError as exc:
        # Nothing has been written at this point. Saying so matters: an operator who
        # believes a half-valid file landed will debug the wrong thing.
        return False, f"校验未通过，未写入任何内容：{exc}"

    if result.empty:
        return True, f"{path} 无改动"

    config_write.write_atomic(path, result.rendered)
    return True, f"{path} 已写入（{', '.join(result.changed_fields) or '-'}）"


# ------------------------------------------------------------------------- the wizard
def run(args: Any) -> int:
    """Entry point called from :mod:`soapbot.cli`. Never raises for expected input errors."""
    interactive = _interactive() and not getattr(args, "non_interactive", False)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    config_dir = Path(settings.config_dir)
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"配置目录不可用：{config_dir}（{exc}）", file=sys.stderr)
        return EXIT_NOT_WRITTEN

    print(f"配置文件目录：{config_dir}")
    print("（与面板写入的是同一个目录；这里写的改动同样需要重启才生效）\n")

    if not getattr(args, "skip_provider", False):
        code = _setup_provider(args, interactive)
        if code != EXIT_OK:
            return code

    if not getattr(args, "skip_adapter", False):
        code = _setup_adapter(args, interactive)
        if code != EXIT_OK:
            return code

    _print_next_steps(interactive)
    return EXIT_OK


def _setup_provider(args: Any, interactive: bool) -> int:
    path = settings.providers_file
    print("== Provider（上游模型端点）==")
    print(f"目标文件：{path}")

    provider_id = getattr(args, "provider_id", "") or ""
    base_url = getattr(args, "base_url", "") or ""
    model = getattr(args, "model", "") or ""
    key = _api_key_value(args)

    if interactive:
        provider_id = provider_id or _ask("Provider ID", "deepseek")
        base_url = base_url or _ask("base_url（含 /v1）", "https://api.deepseek.com/v1")
        model = model or _ask("模型 ID", "deepseek-chat")
        if not key:
            key = _ask_api_key()

    missing = [
        name
        for name, value in (("provider id", provider_id), ("base_url", base_url), ("model", model))
        if not value
    ]
    if missing:
        print(
            f"缺少必填项：{', '.join(missing)}。非交互模式请用 "
            "--provider-id/--base-url/--model。",
            file=sys.stderr,
        )
        return EXIT_BAD_INPUT

    written, message = _write(
        path,
        provider_patch(provider_id=provider_id, base_url=base_url, model=model, api_key=key),
        adapters=False,
    )
    print(message)
    if not written:
        return EXIT_NOT_WRITTEN
    if not key:
        print("  （未提供新密钥：保留文件中已有的 api_key）")
    print()
    return EXIT_OK


def _setup_adapter(args: Any, interactive: bool) -> int:
    path = settings.adapters_file
    print("== 适配器（QQ 接入）==")
    print(f"目标文件：{path}")

    kind = getattr(args, "kind", "") or "onebot11"
    mode = (getattr(args, "mode", "") or "").lower()
    ws_url = getattr(args, "ws_url", "") or ""
    host = getattr(args, "host", "") or ""
    port = getattr(args, "port", None)
    account_id = getattr(args, "account_id", "") or ""
    token = _access_token_value(args)

    if interactive:
        kind = kind or _ask("适配器类型", "onebot11")
        mode = _ask_choice("连接方式", ("forward", "reverse"), mode or "forward")
        account_id = account_id or _ask("机器人 QQ（可留空）", "")
        if mode == "reverse":
            host = host or _ask("监听地址", "127.0.0.1")
            port = port or int(_ask("监听端口", "6700") or 6700)
        else:
            ws_url = ws_url or _ask("NapCat/Lagrange 的 WS 地址", "ws://127.0.0.1:3001")
        if not token:
            token = _ask_access_token()

    if mode not in ("forward", "reverse"):
        print(f"连接方式只能是 forward/reverse，收到 {mode or '(空)'}。", file=sys.stderr)
        return EXIT_BAD_INPUT
    if mode == "forward" and not ws_url:
        print("forward 模式需要 --ws-url（例如 ws://127.0.0.1:3001）。", file=sys.stderr)
        return EXIT_BAD_INPUT
    if mode == "reverse" and not token:
        # Startup refuses a reverse listener with no token: an open port is the whole
        # pipeline exposed to whoever connects first. Failing here is kinder than a
        # boot-time error the operator finds after restarting.
        print(
            "reverse 模式必须配置 access_token（否则启动会拒绝监听）。\n"
            "用 --access-token-env OB_TOKEN 指向环境变量，或交互输入。",
            file=sys.stderr,
        )
        return EXIT_BAD_INPUT

    written, message = _write(
        path,
        adapter_patch(
            kind=kind,
            mode=mode,
            account_id=account_id,
            ws_url=ws_url,
            host=host,
            port=port,
            access_token=token,
        ),
        adapters=True,
    )
    print(message)
    if not written:
        return EXIT_NOT_WRITTEN
    print()
    return EXIT_OK


# ------------------------------------------------------------------------- key input
def _api_key_value(args: Any) -> str:
    """``env:VAR`` from ``--api-key-env``, a literal from ``--api-key``, else nothing."""
    env_name = str(getattr(args, "api_key_env", "") or "").strip()
    if env_name:
        return f"env:{env_name}"
    return str(getattr(args, "api_key", "") or "").strip()


def _access_token_value(args: Any) -> str:
    env_name = str(getattr(args, "access_token_env", "") or "").strip()
    if env_name:
        return f"env:{env_name}"
    return str(getattr(args, "access_token", "") or "").strip()


def _ask_api_key() -> str:
    """Ask for a key **without echoing it**, and prefer a reference over a literal.

    ``getpass`` rather than ``input``: this prompt is answered on a shared terminal as
    often as not, and a key typed in clear text is a key in the scrollback buffer.
    """
    import getpass

    choice = _ask_choice(
        "密钥存放方式：env 表示只写变量名，literal 表示直接写入文件",
        ("env", "literal", "skip"),
        "env",
    )
    if choice == "skip":
        return ""
    if choice == "env":
        name = _ask("环境变量名", "DEEPSEEK_API_KEY")
        return f"env:{name}" if name else ""
    try:
        value = getpass.getpass("API Key（输入不回显）: ").strip()
    except EOFError:
        return ""
    if value:
        print("  注意：字面量密钥会写进配置文件；建议改用 env: 引用。")
    return value


def _ask_access_token() -> str:
    import getpass

    choice = _ask_choice(
        "access_token 存放方式",
        ("env", "literal", "skip"),
        "env",
    )
    if choice == "skip":
        return ""
    if choice == "env":
        name = _ask("环境变量名", "ONEBOT_ACCESS_TOKEN")
        return f"env:{name}" if name else ""
    try:
        return getpass.getpass("access_token（输入不回显）: ").strip()
    except EOFError:
        return ""


# ------------------------------------------------------------------------- next steps
def _print_next_steps(interactive: bool) -> None:
    host = settings.host if settings.host not in ("0.0.0.0", "::") else "127.0.0.1"
    url = f"http://{host}:{settings.port}"
    print("== 下一步 ==")
    print("1. 启动服务：soapbot start")
    print(f"2. 打开面板：{url}")
    print("3. 登录令牌：soapbot token  # 一次性凭据，登录后即失效")
    print("4. 改动需要重启进程才生效（配置在启动时读取）。")
    if interactive:
        print("\n提示：面板的「测试」按钮可以在保存前验证地址是否可达，不必反复重启试错。")

"""One error vocabulary for the HTTP edge.

Before this existed, twenty-odd handlers put the exception text straight into the
response ``detail``.
That puts a config parser's message, a plugin's exception text and sometimes a path
straight into the browser. The operator needs those words; the caller of an API does
not. Now the full exception goes to the server log with its locating fields, and the
response carries a stable code plus a short sentence that is safe to display.

The existing exception families (``ConfigError`` in core, ``ProviderError``,
``IsolationError``) are not rewritten. They keep their own inheritance and are
mapped here by kind when a handler wants to raise an AppError instead.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base for errors that cross the HTTP boundary."""

    kind = "internal"

    def __init__(self, message: str = "", *, detail: str = "") -> None:
        super().__init__(message)
        #: Server-side diagnosis. Never serialised into a response.
        self.detail = detail or message


class ConfigError(AppError):
    kind = "config"


class AuthError(AppError):
    kind = "auth"


class UpstreamError(AppError):
    kind = "upstream"


class PluginError(AppError):
    kind = "plugin"


class RateLimitError(AppError):
    kind = "rate_limit"


class InternalError(AppError):
    kind = "internal"


STATUS_BY_KIND: dict[str, int] = {
    "config": 422,
    "auth": 401,
    "upstream": 502,
    "plugin": 400,
    "rate_limit": 429,
    "internal": 500,
}

SAFE_MESSAGES: dict[str, str] = {
    "config": "配置文件无法读取或格式不正确，请检查服务端日志",
    "auth": "凭据无效或已过期",
    "upstream": "上游服务暂时不可用",
    "plugin": "插件请求无法完成",
    "rate_limit": "请求过于频繁，请稍后重试",
    "internal": "服务内部错误，请检查服务端日志",
}

#: Status codes used by handlers that still raise HTTPException directly. The
#: sentence is deliberately generic: it says what happened, not why it happened.
_SAFE_BY_STATUS: dict[int, str] = {
    400: "请求无法完成",
    401: "凭据无效或已过期",
    403: "没有执行该操作的权限",
    404: "请求的资源不存在",
    409: "内容已被他人修改，请重新确认",
    413: "请求体过大",
    422: "提交的内容无法通过校验",
    429: "请求过于频繁，请稍后重试",
    502: "上游服务暂时不可用",
    503: "服务尚未就绪",
}


#: A response may name the *category* of the problem, never the exception text.
#: An operator seeing "traversal" or "YAML" knows what to fix; the archive entry
#: name, the file path and the upstream body stay in the server log. Matching a
#: fixed vocabulary is what makes this safe — echoing str(exc) would not be.
_SAFE_REASON_LABELS: tuple[tuple[str, str], ...] = (
    ("yaml", "YAML"),
    ("path traversal", "traversal"),
    ("escapes", "escapes"),
    ("symlink", "symlink"),
    ("not a zip", "not a zip archive"),
    ("too many entries", "too many entries"),
    ("decompression", "decompression bomb"),
    ("stale", "stale base"),
)

#: The name of an unset environment variable is a reference the operator wrote
#: into their own config, not a secret. Its value is never present.
_ENV_REF_RE = re.compile(r"environment variable\s+'?([A-Z][A-Z0-9_]{2,63})'?")


def safe_detail(status: int, exc: Exception, origin: str, **fields: Any) -> str:
    """Log the real exception, return a short sentence plus a controlled label.

    ``origin`` is a module or handler name, not the exception text. It gives an
    operator one stable word to grep for without putting a file path in the response.
    """
    extra = " ".join(f"{key}={value}" for key, value in fields.items() if value)
    logger.warning(
        "handled error origin=%s type=%s status=%d %s",
        origin,
        type(exc).__name__,
        status,
        extra,
        exc_info=True,
    )
    text = str(exc)
    lower = text.lower()
    labels = [label for needle, label in _SAFE_REASON_LABELS if needle in lower]
    # Only config parsing may name a referenced variable, and only when the
    # message is the specific "unset environment variable" one. Applying this to
    # any exception would let an uploaded archive entry name call itself
    # "environment variable 'SOMETHING'" and have SOMETHING reflected in a
    # response the operator reads as a diagnosis.
    if origin.startswith("config_") and "unset environment variable" in lower:
        labels.extend(_ENV_REF_RE.findall(text))
    suffix = ", ".join(dict.fromkeys(labels))[:120]
    base = _SAFE_BY_STATUS.get(status, "请求未能完成")
    return f"{base}（{suffix}）" if suffix else base


def install_error_handlers(app: FastAPI) -> None:
    """Register the AppError handler. Call once from ``create_app``.

    FastAPI's built-in HTTPException handler is left alone: it already returns a
    controlled ``detail`` and the handlers here all pass it an explicitly safe
    string. A catch-all Exception handler is deliberately not installed — the
    framework's default 500 contains no traceback, and swallowing unexpected
    exceptions would hide the very bug a test is trying to surface.
    """

    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        status = STATUS_BY_KIND.get(exc.kind, 500)
        # Do not put ``exc.detail`` in the message: the ring buffer echoes messages
        # to the panel. exc_info carries the full diagnosis to the server-side
        # stream, where the logging filter redacts credential-shaped text.
        logger.warning(
            "app error kind=%s status=%d type=%s",
            exc.kind,
            status,
            type(exc).__name__,
            exc_info=True,
        )
        return JSONResponse(
            status_code=status,
            content={"detail": SAFE_MESSAGES[exc.kind], "code": f"err.{exc.kind}"},
        )

    app.add_exception_handler(AppError, _app_error)

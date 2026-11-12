"""A vetted gateway to QQ 空间 through the operator's own protocol endpoint.

QQ's official bot platform has no 空间/说说 API at all. The only route is a
personal-account protocol endpoint (NapCat / Lagrange), which README and
SECURITY.md treat as a risk area: personal-account automation can trigger platform
risk controls and get the account frozen. Therefore:

* the whole gateway is **off** unless ``SOAPBOT_QZONE_VIA_PROTOCOL=true``;
* the endpoint is named explicitly by the operator, never discovered;
* only four OneBot-style actions are callable, split into read and write sets —
  a plugin holding ``qzone_read`` cannot reach ``send_qzone_post`` by guessing;
* the access token stays with the host and is never passed to, or returned to, a
  plugin; audit records the action and text length, never the text.

This is a protocol gateway, not a scraper. It does not log in, does not hold a
cookie, and does not bypass any platform control. The operator must already run a
protocol endpoint they are entitled to use, and accepts the account risk.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

READ_ACTIONS = frozenset({"get_friend_feeds", "get_user_feeds"})
WRITE_ACTIONS = frozenset({"send_qzone_post"})
MAX_RESPONSE_CHARS = 64 * 1024
MAX_TEXT_CHARS = 2000


class QzoneUnavailableError(RuntimeError):
    """Raised when the operator has not explicitly enabled the protocol route."""


class QzoneGateway:
    """Fail-closed bridge to a OneBot-compatible HTTP API endpoint."""

    def __init__(self, *, settings: Any = None, client: Any = None) -> None:
        self._settings = settings
        self._client = client

    def _cfg(self):
        if self._settings is not None:
            return self._settings
        from soapbot.config import settings

        return settings

    def enabled(self) -> bool:
        return bool(getattr(self._cfg(), "qzone_via_protocol", False))

    def _base_url(self) -> str:
        cfg = self._cfg()
        url = str(getattr(cfg, "qzone_api_url", "") or "").strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise QzoneUnavailableError("a qzone_api_url is required")
        return url + "/"

    def _token(self) -> str:
        secret = getattr(self._cfg(), "qzone_access_token", "")
        return (
            secret.get_secret_value()
            if hasattr(secret, "get_secret_value")
            else str(secret or "")
        )

    async def call(self, action: str, params: dict[str, Any], *, write: bool) -> dict:
        """Call exactly one allow-listed action on the protocol endpoint."""
        if not self.enabled():
            raise QzoneUnavailableError(
                "qzone is disabled; set SOAPBOT_QZONE_VIA_PROTOCOL=true only if you "
                "accept the personal-account risk"
            )
        allowed = WRITE_ACTIONS if write else READ_ACTIONS
        if action not in allowed:
            raise ValueError("qzone action is not allow-listed")

        params = dict(params)  # never mutate a caller's dict
        text = str(params.pop("text", "") or "")
        if write:
            if not text or len(text) > MAX_TEXT_CHARS:
                raise ValueError("a post needs text of 1..2000 characters")
            if params.pop("confirm", None) is not True:
                raise ValueError("a post needs an explicit confirm=true")
            params["text"] = text

        from soapbot.net.client import outbound_client

        token = self._token()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with outbound_client(client=self._client) as http:
            response = await http.post(
                urljoin(self._base_url(), action), json=params, headers=headers
            )
        status = int(getattr(response, "status_code", 0))
        if status >= 400:
            # The body may echo the post text; report only the status.
            raise RuntimeError(f"qzone endpoint returned HTTP {status}")
        body = getattr(response, "text", "") or ""
        if len(body) > MAX_RESPONSE_CHARS:
            raise RuntimeError("qzone response exceeds the size cap")
        return {"status": status, "chars": len(body), "text": body}

"""OneBot 11 gateway.

This package exposes an adapter that does *not* speak OneBot (currently the
official QQ bot) to OneBot 11 clients. It is the reverse of
``soapbot.adapters.onebot11``: that module is a client of a protocol end, this is
a server an OneBot client connects to.

It deliberately does not implement the QQ protocol, log in to an account, or
bypass platform review. See ``docs/onebot-gateway.md`` for the boundary.
"""

from __future__ import annotations

from soapbot.gateway.onebot11 import GatewayError, OneBot11Gateway

__all__ = ["GatewayError", "OneBot11Gateway"]

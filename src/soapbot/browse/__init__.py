"""Read-only access to public web pages for purchase proposals.

The host owns this surface, not the plugin: a plugin asks for a URL, and the host
decides whether the destination is allowed, whether robots.txt permits it, and how
much of the response is allowed in. No cookie, no login state, no form submission,
no redirect following, no JavaScript execution.
"""

from __future__ import annotations

from soapbot.browse.reader import PageSnapshot, ReadError, read_public_page

__all__ = ["PageSnapshot", "ReadError", "read_public_page"]

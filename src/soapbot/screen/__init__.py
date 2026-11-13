"""Screen capability: the bot looks at its dedicated machine's display.

Phase 1 of ``docs/autonomous-capabilities-design.md`` §1 — view only. Frames are
captured by the host, handed to the model context through the host-owned inbox,
and never persisted, audited by content, or exposed to plugin code. The control
plane (input injection — actually *playing*) is a separate phase with its own
three preconditions and stays closed.
"""

from soapbot.screen.capture import (
    ScreenPolicy,
    ScreenRefusedError,
    ScreenUnavailableError,
    capture_tile,
)
from soapbot.screen.inbox import SCREEN_INBOX, ScreenInbox

__all__ = [
    "SCREEN_INBOX",
    "ScreenInbox",
    "ScreenPolicy",
    "ScreenRefusedError",
    "ScreenUnavailableError",
    "capture_tile",
]

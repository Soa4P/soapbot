"""Screen capture: the bot looks at its own dedicated machine. View-only.

Design contract: ``docs/autonomous-capabilities-design.md`` §1. Five hard
boundaries, each enforced here rather than promised:

1. **Dedicated machine only** — capture is refused unless the operator declared
   this exact hostname as the bot's work machine (``SOAPBOT_SCREEN_DEDICATED_MACHINE``);
   an empty declaration means "no machine is dedicated", i.e. always refuse.
2. **Frames go one way** — into the model context via :mod:`soapbot.screen.inbox`.
   Nothing here writes a file, an audit detail, or a log line containing pixels.
3. **Quota** — the ``SCREEN`` capability is in ``SENSITIVE_CAPABILITIES``, so the
   guard's 30/min sensitive sliding window applies to plugin calls; the host
   ``/look`` command path is additionally bounded by the frames-per-request cap.
4. **View only** — no input injection exists in this module, and no other module
   may add it in phase 1 (the control plane has its own three preconditions).
5. **Session visibility** — the audit records which session asked, how many frames,
   how long, how many bytes; never what was on screen.
"""

from __future__ import annotations

import asyncio
import base64
import io
import socket
import time
from dataclasses import dataclass
from typing import Any

from PIL import Image

from soapbot.ai.vision import ImagePayload, _fit, frame_signature, tile_frames

MAX_FRAMES_PER_REQUEST = 6


class ScreenRefusedError(RuntimeError):
    """A policy gate refused the capture. ``reason`` is a short stable token."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ScreenUnavailableError(RuntimeError):
    """The ``mss`` capture dependency is not installed."""

    def __init__(self) -> None:
        super().__init__(
            "screen capture needs the optional dependency mss; "
            "install it with: pip install 'soapbot[screen]'"
        )


@dataclass(slots=True)
class TileResult:
    """Metadata about one capture. The pixels travel separately (``payload``)."""

    payload: ImagePayload
    frames_captured: int
    frames_used: int
    frames_dropped: int
    duration_ms: int
    size_bytes: int


@dataclass(slots=True)
class ScreenPolicy:
    enabled: bool = False
    dedicated_machine: str = ""
    frames_max: int = 6
    interval_ms: int = 500

    @classmethod
    def from_settings(cls, settings: Any) -> ScreenPolicy:
        return cls(
            enabled=bool(getattr(settings, "screen_enabled", False)),
            dedicated_machine=str(getattr(settings, "screen_dedicated_machine", "") or "").strip(),
            frames_max=max(1, min(MAX_FRAMES_PER_REQUEST, int(getattr(settings, "screen_frames_max", 6) or 6))),
            interval_ms=max(0, int(getattr(settings, "screen_capture_interval_ms", 500) or 0)),
        )

    def check_machine(self, *, hostname: str | None = None) -> None:
        """Raise :class:`ScreenRefusedError` unless this host is the declared one.

        The comparison is case-insensitive: Windows hostnames are case-preserving
        but every writer on earth types them differently.
        """
        if not self.enabled:
            raise ScreenRefusedError("screen_disabled")
        declared = self.dedicated_machine.lower()
        if not declared:
            # An empty declaration is "no machine is dedicated": fail closed.
            raise ScreenRefusedError("screen_machine_undeclared")
        current = (hostname if hostname is not None else socket.gethostname()).lower()
        if current != declared:
            raise ScreenRefusedError("screen_machine_mismatch")


def _grab_image(mss_module: Any) -> Image.Image:
    """One synchronous mss grab, converted to a Pillow RGB image in memory."""
    with mss_module.mss() as scanner:
        shot = scanner.grab(scanner.monitors[1])  # monitor 1 = the primary display
    # mss returns BGRA; Pillow reads raw BGRA with the matching mode.
    img = Image.frombytes("RGBA", shot.size, shot.bgra, "raw", "BGRA")
    return img.convert("RGB")


async def capture_tile(
    policy: ScreenPolicy,
    *,
    frames: int = 1,
    interval_ms: int | None = None,
    hostname: str | None = None,
) -> TileResult:
    """Capture ``frames`` screenshots, drop near-duplicates, tile into one image.

    Frames are sampled over time (``interval_ms`` apart) so the model sees change,
    not six copies of one static screen. The whole pipeline stays in memory:
    grabs → Pillow images → one grid → PNG bytes → base64, then the raw frames
    are released when this function returns.
    """
    policy.check_machine(hostname=hostname)
    frames = max(1, min(frames, policy.frames_max))
    pause = policy.interval_ms if interval_ms is None else max(0, interval_ms)
    started = time.monotonic()

    try:
        import mss as mss_module
    except ImportError as exc:  # optional dependency, same wording as edge-tts
        raise ScreenUnavailableError() from exc

    grabbed: list[Image.Image] = []
    for index in range(frames):
        if index and pause:
            await asyncio.sleep(pause / 1000.0)
        grabbed.append(await asyncio.to_thread(_grab_image, mss_module))

    # Near-identical frames carry no information and cost grid cells: keep the
    # first of each visually distinct run (the first frame is always kept).
    picked: list[Image.Image] = []
    signatures: set[bytes] = set()
    for img in grabbed:
        sig = frame_signature(img)
        if sig in signatures:
            continue
        signatures.add(sig)
        picked.append(_fit(img))
    frames_dropped = len(grabbed) - len(picked)
    if not picked:
        # Degenerate only if ``grabbed`` was empty, which cannot happen (frames >= 1);
        # kept as a guard for defensive completeness.
        picked = [_fit(grabbed[0])]

    grid = tile_frames(picked)
    buf = io.BytesIO()
    grid.save(buf, format="PNG")
    png = buf.getvalue()
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    payload = ImagePayload(
        data_url=data_url,
        mime="image/png",
        width=grid.width,
        height=grid.height,
        is_animated=False,
        frame_count=len(picked),
        sampled_frames=len(picked),
    )
    return TileResult(
        payload=payload,
        frames_captured=len(grabbed),
        frames_used=len(picked),
        frames_dropped=frames_dropped,
        duration_ms=int((time.monotonic() - started) * 1000),
        size_bytes=len(png),
    )

"""Vision pipeline: static images and animated GIFs.

The interesting case is animation. Most multimodal endpoints accept *one* image
per part and will not animate a GIF — feeding raw GIF bytes yields a description
of the first frame at best. So for animated images we:

  1. decode with Pillow, count frames
  2. sample N evenly-spaced frames (default 6), skipping near-duplicates
  3. tile them into a single grid image with index labels
  4. send that grid as one image, and tell the model it is a frame grid

That keeps it to a single image payload (cheap, broadly supported) while still
conveying motion.

Descriptions are cached by content hash so history replay costs no tokens and no
API calls: old turns carry the cached text, never the image.
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

MAX_EDGE = 1024
"""Downscale so a single request stays reasonable."""

GRID_COLUMNS = 3
DEFAULT_FRAMES = 6


@dataclass(slots=True)
class ImagePayload:
    """What we hand to the provider."""

    data_url: str
    mime: str
    width: int
    height: int
    is_animated: bool = False
    frame_count: int = 1
    sampled_frames: int = 1
    note: str = ""


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def _to_data_url(img: Image.Image, fmt: str = "PNG") -> tuple[str, str]:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    mime = "image/png" if fmt == "PNG" else "image/jpeg"
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:{mime};base64,{b64}", mime


def _fit(img: Image.Image, max_edge: int = MAX_EDGE) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= max_edge:
        return img
    scale = max_edge / float(longest)
    return img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)


def _frame_signature(img: Image.Image, size: int = 16) -> bytes:
    """Cheap perceptual signature used to drop duplicated GIF frames."""
    small = img.convert("L").resize((size, size), Image.LANCZOS)
    return small.tobytes()


def prepare_image(data: bytes, *, max_frames: int = DEFAULT_FRAMES, label_frames: bool = True) -> ImagePayload:
    """Turn raw bytes into a single image payload, tiling animated images."""
    img = Image.open(io.BytesIO(data))
    frame_count = int(getattr(img, "n_frames", 1) or 1)

    if frame_count <= 1:
        rgb = _fit(img.convert("RGB"))
        data_url, mime = _to_data_url(rgb)
        return ImagePayload(
            data_url=data_url,
            mime=mime,
            width=rgb.width,
            height=rgb.height,
            is_animated=False,
            frame_count=1,
            sampled_frames=1,
        )

    # --- animated: sample distinct frames ---
    step = max(1, frame_count // max_frames)
    picked: list[Image.Image] = []
    signatures: set[bytes] = set()
    for idx in range(0, frame_count, step):
        try:
            img.seek(idx)
        except EOFError:
            break
        frame = img.convert("RGB")
        sig = _frame_signature(frame)
        if sig in signatures:
            continue  # near-identical frame, skip to keep the grid informative
        signatures.add(sig)
        picked.append(_fit(frame))
        if len(picked) >= max_frames:
            break

    if not picked:
        img.seek(0)
        picked = [_fit(img.convert("RGB"))]

    grid = _tile(picked, label_frames=label_frames)
    data_url, mime = _to_data_url(grid)
    note = (
        f"这是一张动图，已抽取 {len(picked)} 帧（原图共 {frame_count} 帧）拼成网格，"
        "按从左到右、从上到下的时间顺序展示。请结合多帧变化理解动作过程。"
    )
    return ImagePayload(
        data_url=data_url,
        mime=mime,
        width=grid.width,
        height=grid.height,
        is_animated=True,
        frame_count=frame_count,
        sampled_frames=len(picked),
        note=note,
    )


def _tile(frames: list[Image.Image], *, label_frames: bool = True) -> Image.Image:
    count = len(frames)
    cols = min(GRID_COLUMNS, count)
    rows = (count + cols - 1) // cols
    cell_w = max(f.width for f in frames)
    cell_h = max(f.height for f in frames)
    pad = 4
    label_h = 18 if label_frames else 0

    canvas = Image.new(
        "RGB",
        (cols * cell_w + pad * (cols + 1), rows * (cell_h + label_h) + pad * (rows + 1)),
        (24, 24, 28),
    )
    draw = ImageDraw.Draw(canvas)
    for i, frame in enumerate(frames):
        col = i % cols
        row = i // cols
        x = pad + col * (cell_w + pad)
        y = pad + row * (cell_h + label_h + pad)
        canvas.paste(frame, (x, y))
        if label_frames:
            draw.text((x + 2, y + cell_h + 2), f"#{i + 1}", fill=(180, 220, 255))
    return canvas


def prepare_from_path(path: Path, **kwargs) -> ImagePayload:
    return prepare_image(path.read_bytes(), **kwargs)


class DescriptionCache:
    """Persist image description text keyed by content hash.

    This is what lets Wave 3 store only text in conversation history: replaying a
    conversation re-reads the description instead of re-uploading the image.
    """

    def __init__(self, capacity: int = 2000) -> None:
        self._cache: dict[str, str] = {}
        self._capacity = capacity

    def get(self, key: str) -> str | None:
        return self._cache.get(key)

    def put(self, key: str, description: str) -> None:
        if len(self._cache) >= self._capacity:
            # drop oldest insertion
            self._cache.pop(next(iter(self._cache)), None)
        self._cache[key] = description

    def __len__(self) -> int:
        return len(self._cache)

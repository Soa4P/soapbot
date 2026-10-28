"""Value types for the Bilibili watcher.

Kept separate from the client so the command layer, the impression generator and the
management API all describe a video the same way. A dict passed between three modules
would inevitably grow three different key names for "how many plays".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class VideoStat:
    view: int = 0
    danmaku: int = 0
    reply: int = 0
    like: int = 0
    coin: int = 0
    favorite: int = 0
    share: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "view": self.view,
            "danmaku": self.danmaku,
            "reply": self.reply,
            "like": self.like,
            "coin": self.coin,
            "favorite": self.favorite,
            "share": self.share,
        }


@dataclass(slots=True)
class VideoInfo:
    bvid: str
    aid: int = 0
    title: str = ""
    description: str = ""
    duration_seconds: int = 0
    published_at: float = 0.0
    author: str = ""
    author_mid: int = 0
    cover_url: str = ""
    category: str = ""
    url: str = ""
    pages: int = 1
    stat: VideoStat = field(default_factory=VideoStat)

    @property
    def duration_text(self) -> str:
        total = max(0, self.duration_seconds)
        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "bvid": self.bvid,
            "aid": self.aid,
            "title": self.title,
            "description": self.description,
            "duration_seconds": self.duration_seconds,
            "duration_text": self.duration_text,
            "published_at": self.published_at,
            "author": self.author,
            "author_mid": self.author_mid,
            "category": self.category,
            "url": self.url,
            "pages": self.pages,
            "stat": self.stat.to_dict(),
        }


@dataclass(slots=True)
class Comment:
    author: str = ""
    content: str = ""
    likes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"author": self.author, "content": self.content, "likes": self.likes}


@dataclass(slots=True)
class WatchReport:
    """A video plus a written impression of it."""

    video: VideoInfo
    impression: str = ""
    comments: list[Comment] = field(default_factory=list)
    model: str = ""
    tier: str = ""
    degraded: bool = ""
    """Non-empty when the impression is a metadata summary rather than model output.

    Recorded explicitly instead of leaving ``impression`` empty: the caller has to be
    able to say "这是我的看法" versus "模型没有配置，只能读标题" — passing a template off
    as generated text would be the kind of quiet dishonesty that gets noticed later.
    """

    def to_dict(self) -> dict[str, Any]:
        return {
            "video": self.video.to_dict(),
            "impression": self.impression,
            "comments": [c.to_dict() for c in self.comments],
            "model": self.model,
            "tier": self.tier,
            "degraded": self.degraded,
        }


__all__ = ["Comment", "VideoInfo", "VideoStat", "WatchReport"]

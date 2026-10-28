"""Bilibili watching: public metadata plus a written impression.

Tiers, as they are implemented (not as they are marketed):

* ``l1`` — unsigned public endpoints. Video detail, hot comments, uploader card.
* ``l2`` — adds wbi-signed requests so the space and search endpoints accept them.
  Still no cookie and no login.
* ``l3`` — **rejected**. It would require a logged-in session cookie, which this
  project does not hold and the README's disclaimer says the operator must decide
  about themselves. Accepting the string and behaving like L2 would make the tier
  setting meaningless.

Enable with ``SOAPBOT_ENABLE_BILIBILI=true``. Off by default.
"""

from soapbot.bilibili.client import (
    BilibiliClient,
    BilibiliError,
    BilibiliNotFoundError,
    BilibiliRateLimitedError,
    BilibiliRiskControlError,
    BilibiliTierError,
    from_settings,
    is_short_link,
    parse_target,
)
from soapbot.bilibili.commands import BilibiliCommands
from soapbot.bilibili.models import Comment, VideoInfo, VideoStat, WatchReport
from soapbot.bilibili.watcher import VideoWatcher

__all__ = [
    "BilibiliClient",
    "BilibiliCommands",
    "BilibiliError",
    "BilibiliNotFoundError",
    "BilibiliRateLimitedError",
    "BilibiliRiskControlError",
    "BilibiliTierError",
    "Comment",
    "VideoInfo",
    "VideoStat",
    "VideoWatcher",
    "WatchReport",
    "from_settings",
    "is_short_link",
    "parse_target",
]

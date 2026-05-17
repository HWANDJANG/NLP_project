"""Crawler configuration: board mapping, collection limits, env loading."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "raw"

load_dotenv(PROJECT_ROOT / ".env")

BASE_URL = "https://www.ssodam.com"


@dataclass(frozen=True)
class BoardSpec:
    name: str          # display name used in saved JSONL
    board_id: int      # numeric id used in /board/{board_id}/{page}
    target_posts: int  # how many posts to collect for this board


BOARDS: dict[str, BoardSpec] = {
    "익게2":   BoardSpec(name="익게2",   board_id=5,  target_posts=150),
    "연애상담소": BoardSpec(name="연애상담소", board_id=6,  target_posts=100),
    "정치":    BoardSpec(name="정치",    board_id=86, target_posts=80),
    "취업게시판": BoardSpec(name="취업게시판", board_id=11, target_posts=80),
}


@dataclass(frozen=True)
class CrawlLimits:
    min_comments_per_post: int = 3
    max_comments_per_post: int = 10
    min_comment_chars: int = 5


@dataclass(frozen=True)
class HttpSettings:
    cookie: str = field(default_factory=lambda: os.environ.get("SSODAM_COOKIE", ""))
    user_agent: str = field(
        default_factory=lambda: os.environ.get(
            "SSODAM_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
    )
    request_delay: float = field(
        default_factory=lambda: float(os.environ.get("SSODAM_REQUEST_DELAY", "1.5"))
    )
    ssl_verify: bool = field(
        default_factory=lambda: os.environ.get("SSODAM_SSL_VERIFY", "true").lower()
        not in ("0", "false", "no")
    )


LIMITS = CrawlLimits()
HTTP = HttpSettings()

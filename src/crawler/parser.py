"""HTML parsers for ssodam board list and post detail.

Confirmed against:
  - list page  : https://www.ssodam.com/board/5/1
  - detail page: https://www.ssodam.com/content/2023442
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .config import BASE_URL, BoardSpec

log = logging.getLogger(__name__)

# Author name used by the site for the post's original author when they reply
# to their own comment thread. Their replies are not user reactions, so we tag
# them so downstream filtering can drop them from training data if desired.
POST_AUTHOR_LABEL = "글쓴이"


@dataclass
class PostStub:
    """Minimal info pulled from a board list page."""
    post_id: str
    url: str
    title: str
    comment_count_hint: int  # parsed from "[N]" on the list row; used to pre-filter


@dataclass
class Comment:
    comment_id: str
    author: str
    depth: int
    is_author: bool
    created_at: str | None
    text: str


@dataclass
class PostDetail:
    post_id: str
    title: str
    body: str
    url: str
    created_at: str | None
    views: int | None
    comments: list[Comment]


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------

def board_list_url(board: BoardSpec, page: int) -> str:
    return f"{BASE_URL}/board/{board.board_id}/{page}"


def post_detail_url(post_id: str | int) -> str:
    return f"{BASE_URL}/content/{post_id}"


# ---------------------------------------------------------------------------
# List-page parser
# ---------------------------------------------------------------------------

_POST_ID_FROM_HREF = re.compile(r"/content/(\d+)")
_COMMENT_NUM = re.compile(r"\[(\d+)\]")
_COMMENT_ID_FROM_TAG = re.compile(r"comments_(\d+)")
_INT_IN_TEXT = re.compile(r"-?\d+")


def parse_board_list(html: str) -> list[PostStub]:
    """Extract user post stubs from a board list page. Skips notices/ads."""
    soup = BeautifulSoup(html, "lxml")
    stubs: list[PostStub] = []

    for tr in soup.select("table.table tbody tr"):
        title_cell = tr.select_one("td.title.title-align")
        if title_cell is None:
            continue
        if title_cell.select_one("span.label.label-info, span.label.label-warning"):
            continue  # notice / sponsored row

        anchor = title_cell.select_one('a[href*="/content/"]')
        if anchor is None:
            continue
        m = _POST_ID_FROM_HREF.search(anchor.get("href") or "")
        if not m:
            continue
        post_id = m.group(1)

        title_span = anchor.select_one("span.content-title")
        title = (title_span.get_text(" ", strip=True)
                 if title_span else anchor.get_text(" ", strip=True))

        comment_hint = 0
        comment_el = title_cell.select_one("span.comment-num")
        if comment_el:
            cm = _COMMENT_NUM.search(comment_el.get_text())
            if cm:
                comment_hint = int(cm.group(1))

        stubs.append(
            PostStub(
                post_id=post_id,
                url=urljoin(BASE_URL, f"/content/{post_id}"),
                title=title,
                comment_count_hint=comment_hint,
            )
        )
    return stubs


# ---------------------------------------------------------------------------
# Detail-page parser
# ---------------------------------------------------------------------------

def _parse_comments(soup: BeautifulSoup) -> list[Comment]:
    out: list[Comment] = []
    for c_el in soup.select("div.comment[id^='comments_']"):
        m = _COMMENT_ID_FROM_TAG.match(c_el.get("id") or "")
        if not m:
            continue
        comment_id = m.group(1)

        # `comments_depth` hidden input lives inside each comment block.
        depth = 0
        depth_input = c_el.select_one("input[name='comments_depth']")
        if depth_input is not None:
            try:
                depth = int(depth_input.get("value") or "0")
            except ValueError:
                depth = 0

        user_el = c_el.select_one("div.comment-user")
        author = user_el.get_text(" ", strip=True) if user_el else ""

        # First .comment-date is the timestamp; later .comment-date elements
        # are the "답글" reply button. Take the first text-bearing one that
        # looks like a date.
        created_at = None
        for d in c_el.select("div.comment-date"):
            txt = d.get_text(" ", strip=True)
            if txt and txt != "답글":
                created_at = txt
                break

        body_el = c_el.select_one("div.comment-content")
        if body_el is None:
            continue
        text = body_el.get_text(" ", strip=True)
        if not text:
            continue  # deleted / empty

        is_author = (
            author == POST_AUTHOR_LABEL
            or "comment-user-writer" in (body_el.get("class") or [])
        )

        out.append(
            Comment(
                comment_id=comment_id,
                author=author,
                depth=depth,
                is_author=is_author,
                created_at=created_at,
                text=text,
            )
        )
    return out


def parse_post_detail(html: str, post_id: str, url: str) -> PostDetail | None:
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("div.board-title")
    body_el = soup.select_one("div.board-content")
    if not title_el or not body_el:
        log.debug("post %s: missing title/body", post_id)
        return None

    # Two .board-date elements (PC + mobile) carry the same text — first wins.
    date_el = soup.select_one("div.board-date")
    created_at = date_el.get_text(" ", strip=True) if date_el else None

    views = None
    hits_el = soup.select_one("div.board-hits")
    if hits_el:
        vm = _INT_IN_TEXT.search(hits_el.get_text())
        if vm:
            views = int(vm.group(0))

    return PostDetail(
        post_id=str(post_id),
        title=title_el.get_text(" ", strip=True),
        body=body_el.get_text("\n", strip=True),
        url=url,
        created_at=created_at,
        views=views,
        comments=_parse_comments(soup),
    )


def comment_to_dict(c: Comment) -> dict:
    return asdict(c)

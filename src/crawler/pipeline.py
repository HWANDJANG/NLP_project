"""Orchestrates board-by-board crawling: list -> detail -> store."""
from __future__ import annotations

import logging
from typing import Iterator

from tqdm import tqdm

from .config import BoardSpec, LIMITS
from .http_session import PoliteFetcher
from .parser import (
    Comment,
    PostDetail,
    PostStub,
    board_list_url,
    comment_to_dict,
    parse_board_list,
    parse_post_detail,
)
from .storage import BoardStore

log = logging.getLogger(__name__)


def iter_post_stubs(
    fetcher: PoliteFetcher,
    board: BoardSpec,
    max_pages: int = 50,
) -> Iterator[PostStub]:
    """Yield post stubs across consecutive list pages until empty or max_pages."""
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        url = board_list_url(board, page)
        try:
            resp = fetcher.get(url)
        except Exception as e:
            log.warning("list page failed %s: %s", url, e)
            break

        stubs = parse_board_list(resp.text)
        if not stubs:
            log.info("[%s] no more posts at page %d", board.name, page)
            break

        new_count = 0
        for stub in stubs:
            if stub.post_id in seen:
                continue
            seen.add(stub.post_id)
            new_count += 1
            yield stub
        log.debug("[%s] page %d: %d stubs (%d new)", board.name, page, len(stubs), new_count)
        if new_count == 0:
            # paging may have looped back to the same content
            break


def _is_reaction(c: Comment) -> bool:
    """Comment counts as a reaction-to-the-post if it's not the OP's own reply
    and meets the minimum character length."""
    return (not c.is_author) and len(c.text) >= LIMITS.min_comment_chars


def _qualifies(detail: PostDetail) -> bool:
    reactions = [c for c in detail.comments if _is_reaction(c)]
    return len(reactions) >= LIMITS.min_comments_per_post and bool(detail.body)


def _trim_comments(comments: list[Comment]) -> list[Comment]:
    filtered = [c for c in comments if _is_reaction(c)]
    return filtered[: LIMITS.max_comments_per_post]


def crawl_board(board: BoardSpec, fetcher: PoliteFetcher | None = None) -> int:
    """Crawl one board until `board.target_posts` qualifying posts are stored.

    Returns the number of newly saved posts in this run.
    """
    fetcher = fetcher or PoliteFetcher()
    store = BoardStore(board.name)
    saved_this_run = 0
    needed = max(0, board.target_posts - len(store))
    if needed == 0:
        log.info("[%s] already at target (%d posts)", board.name, len(store))
        return 0

    log.info("[%s] target=%d, existing=%d, need=%d",
             board.name, board.target_posts, len(store), needed)

    progress = tqdm(total=needed, desc=board.name, unit="post")
    try:
        for stub in iter_post_stubs(fetcher, board):
            if store.has(stub.post_id):
                continue
            # The list page already shows comment count — skip cheap so we
            # don't waste a request on posts that can't qualify.
            if stub.comment_count_hint < LIMITS.min_comments_per_post:
                continue

            try:
                resp = fetcher.get(stub.url)
            except Exception as e:
                log.warning("detail fetch failed %s: %s", stub.url, e)
                continue

            detail = parse_post_detail(resp.text, stub.post_id, stub.url)
            if detail is None:
                continue
            if not _qualifies(detail):
                continue

            kept_comments = _trim_comments(detail.comments)
            record = {
                "board": board.name,
                "post_id": detail.post_id,
                "title": detail.title,
                "post": detail.body,
                "url": detail.url,
                "created_at": detail.created_at,
                "views": detail.views,
                "comment_count": len(kept_comments),
                "comments": [comment_to_dict(c) for c in kept_comments],
            }
            if store.append(record):
                saved_this_run += 1
                progress.update(1)

            if len(store) >= board.target_posts:
                log.info("[%s] reached target %d", board.name, board.target_posts)
                break
    finally:
        progress.close()

    return saved_this_run

"""Entry point: `python -m src.crawler [board_name ...]`.

Without arguments, crawls every board defined in config.BOARDS.
"""
from __future__ import annotations

import argparse
import logging
import sys

from .config import BOARDS
from .http_session import PoliteFetcher
from .pipeline import crawl_board


def main() -> int:
    parser = argparse.ArgumentParser(description="ssodam crawler")
    parser.add_argument(
        "boards",
        nargs="*",
        help="Board names to crawl (defaults to all configured boards).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    requested = args.boards or list(BOARDS.keys())
    unknown = [b for b in requested if b not in BOARDS]
    if unknown:
        print(f"Unknown board(s): {unknown}. Known: {list(BOARDS.keys())}", file=sys.stderr)
        return 2

    fetcher = PoliteFetcher()  # reuse one session across boards
    total = 0
    for name in requested:
        added = crawl_board(BOARDS[name], fetcher=fetcher)
        total += added
        print(f"[{name}] saved {added} new posts")
    print(f"Done. Total new posts this run: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

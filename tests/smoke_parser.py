"""Quick offline check that parsers handle the real ssodam HTML.

Run with:
    python -m tests.smoke_parser path/to/board_list.html path/to/post_detail.html
or pipe a single page via stdin:
    Get-Content page.html | python -m tests.smoke_parser - detail
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from src.crawler.parser import parse_board_list, parse_post_detail


def _read(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read()
    return Path(arg).read_text(encoding="utf-8", errors="replace")


def check_list(html: str) -> None:
    stubs = parse_board_list(html)
    print(f"[list] found {len(stubs)} post stubs")
    for s in stubs[:5]:
        print(f"  - {s.post_id} | [{s.comment_count_hint}] {s.title!r}")
    if not stubs:
        sys.exit("list parser returned 0 stubs — selectors may be broken")


def check_detail(html: str, post_id: str = "test") -> None:
    detail = parse_post_detail(html, post_id, url=f"https://www.ssodam.com/content/{post_id}")
    if detail is None:
        sys.exit("detail parser returned None — title or body selector missed")
    rendered = asdict(detail)
    rendered["comments"] = rendered["comments"][:5]  # truncate for display
    print(json.dumps(rendered, ensure_ascii=False, indent=2))
    print(f"\n[detail] total comments parsed: {len(detail.comments)}")
    print(f"[detail] author self-replies: "
          f"{sum(1 for c in detail.comments if c.is_author)}")


def main() -> None:
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "-" and args[1] in {"list", "detail"}:
        html = _read("-")
        (check_list if args[1] == "list" else check_detail)(html)
        return
    if len(args) >= 1:
        check_list(_read(args[0]))
    if len(args) >= 2:
        print()
        check_detail(_read(args[1]))


if __name__ == "__main__":
    main()

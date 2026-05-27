"""Flatten per-board JSONL posts into a single CSV of comments ready for
manual style labeling (a / n / f → Aggressive / Neutral / Friendly).

Columns (label first so it's easy to fill in):
    label, board, post_id, comment_id, depth, title, post, comment

Usage:
    # everything in one file (2,423 rows)
    python -m src.preprocessing.jsonl_to_csv

    # balanced 200 per board, shuffled — good starting point for labeling
    python -m src.preprocessing.jsonl_to_csv --per-board 200 --shuffle
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_OUT = PROJECT_ROOT / "data" / "labeling" / "comments_to_label.csv"

COLUMNS = ["label", "board", "post_id", "comment_id", "depth", "title", "post", "comment"]


def load_rows() -> list[dict]:
    rows: list[dict] = []
    for p in sorted(RAW_DIR.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            post = json.loads(line)
            for c in post["comments"]:
                rows.append({
                    "label": "",
                    "board": post["board"],
                    "post_id": post["post_id"],
                    "comment_id": c["comment_id"],
                    "depth": c["depth"],
                    "title": post["title"],
                    "post": post["post"],
                    "comment": c["text"],
                })
    return rows


def sample(rows: list[dict], per_board: int | None, shuffle: bool, seed: int) -> list[dict]:
    if shuffle:
        random.Random(seed).shuffle(rows)
    if per_board is None:
        return rows
    out: list[dict] = []
    counts: dict[str, int] = {}
    for r in rows:
        n = counts.get(r["board"], 0)
        if n < per_board:
            out.append(r)
            counts[r["board"]] = n + 1
    return out


def write_csv(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Excel opens Korean correctly. QUOTE_ALL so commas/quotes
    # inside post/comment text don't break the row.
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Flatten JSONL posts into a labeling CSV.")
    ap.add_argument("--per-board", type=int, default=None,
                    help="Cap rows per board (default: include every comment).")
    ap.add_argument("--shuffle", action="store_true",
                    help="Shuffle before sampling so labeling sees varied content.")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    rows = load_rows()
    if not rows:
        sys.exit(f"no data found under {RAW_DIR}")
    rows = sample(rows, args.per_board, args.shuffle, args.seed)
    write_csv(rows, args.out)

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["board"]] = counts.get(r["board"], 0) + 1
    print(f"wrote {len(rows)} rows -> {args.out}")
    for b in sorted(counts):
        print(f"  {b}: {counts[b]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

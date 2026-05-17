"""JSONL writer that resumes safely and skips already-seen post IDs."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from .config import DATA_DIR

log = logging.getLogger(__name__)


def _safe_board_filename(board_name: str) -> str:
    # Korean filenames are fine on NTFS, but strip path separators just in case.
    return board_name.replace("/", "_").replace("\\", "_") + ".jsonl"


class BoardStore:
    """Append-only JSONL store, one file per board.

    Each line is a single post record:
        {"board", "post_id", "title", "post", "url", "created_at",
         "comment_count", "comments": [str, ...]}
    """

    def __init__(self, board_name: str, data_dir: Path = DATA_DIR):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / _safe_board_filename(board_name)
        self._seen_ids: set[str] = self._load_existing_ids()
        log.info("Store %s: %d existing posts", self.path.name, len(self._seen_ids))

    def _load_existing_ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        ids: set[str] = set()
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    log.warning("Corrupt line in %s, skipping", self.path.name)
                    continue
                pid = record.get("post_id")
                if pid:
                    ids.add(str(pid))
        return ids

    def has(self, post_id: str) -> bool:
        return str(post_id) in self._seen_ids

    def append(self, record: dict) -> bool:
        pid = str(record.get("post_id") or "")
        if not pid:
            raise ValueError("record must have post_id")
        if pid in self._seen_ids:
            return False
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")
        self._seen_ids.add(pid)
        return True

    def __len__(self) -> int:
        return len(self._seen_ids)


def iter_records(path: Path) -> Iterable[dict]:
    """Helper for downstream preprocessing — read all records back."""
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

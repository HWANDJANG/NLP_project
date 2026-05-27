"""Read the manually labeled xlsx and emit clean training data.

Input  : data/labeling/comments_to_label.xlsx
Outputs: data/labeled/comments_labeled.jsonl  (one comment per line, full record)
         data/labeled/comments_labeled.csv    (utf-8-sig, easy to peek at)

Label scheme (defined by the annotator):
    s = Supportive   — 공감, 위로, 응원, 정서적 지지
    i = Informative  — 정보 전달, 조언, 경험 공유, 일반 의견 (default)
    c = Critical     — 공격, 조롱, 비난, 냉소, 무시
    d = Delete       — 삭제된 댓글 / 의미 없는 댓글 (excluded from training)

Maps cleanly onto the PROJECT_PLAN 3-class scheme: s≈Friendly, i≈Neutral, c≈Aggressive.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

PROJECT_ROOT = Path(__file__).resolve().parents[2]
XLSX_PATH = PROJECT_ROOT / "data" / "labeling" / "comments_to_label.xlsx"
OUT_DIR = PROJECT_ROOT / "data" / "labeled"

LABEL_NAMES = {
    "s": "Supportive",
    "i": "Informative",
    "c": "Critical",
    "d": "Delete",
}
# Optional cleanup: typos / older variants seen in past versions of the file.
LABEL_ALIASES = {"ii": "i", "delete": "d"}
TRAIN_LABELS = {"s", "i", "c"}  # 'd' is dropped


def _to_int(v) -> int | None:
    if v is None:
        return None
    # openpyxl returns numbers as float; cast cleanly.
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _normalize_label(raw) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    return LABEL_ALIASES.get(s, s)


def load_records(path: Path) -> tuple[list[dict], dict]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    header = list(next(rows_iter))
    idx = {col: i for i, col in enumerate(header)}
    needed = ["label", "board", "post_id", "comment_id", "depth", "title", "post", "comment"]
    missing = [c for c in needed if c not in idx]
    if missing:
        sys.exit(f"xlsx is missing columns: {missing}")

    raw_counter: Counter[str] = Counter()
    unknown: Counter[str] = Counter()
    kept: list[dict] = []
    skipped_delete = 0
    skipped_blank = 0

    for row in rows_iter:
        label = _normalize_label(row[idx["label"]])
        raw_counter[label or ""] += 1
        if label is None:
            skipped_blank += 1
            continue
        if label == "d":
            skipped_delete += 1
            continue
        if label not in TRAIN_LABELS:
            unknown[label] += 1
            continue

        kept.append({
            "board": row[idx["board"]],
            "post_id": _to_int(row[idx["post_id"]]),
            "comment_id": _to_int(row[idx["comment_id"]]),
            "depth": _to_int(row[idx["depth"]]) or 0,
            "title": row[idx["title"]] or "",
            "post": row[idx["post"]] or "",
            "comment": row[idx["comment"]] or "",
            "label": label,
            "label_name": LABEL_NAMES[label],
        })

    stats = {
        "raw_label_counts": dict(raw_counter),
        "kept": len(kept),
        "skipped_blank": skipped_blank,
        "skipped_delete": skipped_delete,
        "unknown_labels": dict(unknown),
    }
    return kept, stats


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False))
            f.write("\n")


def write_csv(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["label", "label_name", "board", "post_id", "comment_id",
            "depth", "title", "post", "comment"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in records:
            w.writerow({k: r[k] for k in cols})


def print_stats(records: list[dict], stats: dict) -> None:
    print("Raw label counts in xlsx:")
    for lab, n in sorted(stats["raw_label_counts"].items(), key=lambda x: -x[1]):
        display = lab or "(blank)"
        name = LABEL_NAMES.get(lab, "")
        print(f"  {display:<8} {n:>5}  {name}")
    if stats["unknown_labels"]:
        print(f"\n  ⚠ unknown labels (skipped): {stats['unknown_labels']}")
    print(f"\nKept for training : {stats['kept']}")
    print(f"Dropped (d=Delete): {stats['skipped_delete']}")
    print(f"Dropped (blank)   : {stats['skipped_blank']}")

    # Board × label cross-tab
    cross: dict[str, Counter[str]] = defaultdict(Counter)
    for r in records:
        cross[r["board"]][r["label"]] += 1
    boards = sorted(cross)
    labels = ["s", "i", "c"]
    print("\nBoard × label (kept rows):")
    head = f"  {'board':<12} " + " ".join(f"{l:>5}" for l in labels) + f"  {'total':>6}"
    print(head)
    for b in boards:
        line = f"  {b:<12} " + " ".join(f"{cross[b][l]:>5}" for l in labels)
        line += f"  {sum(cross[b].values()):>6}"
        print(line)


def main() -> int:
    if not XLSX_PATH.exists():
        sys.exit(f"missing: {XLSX_PATH}")
    records, stats = load_records(XLSX_PATH)
    jsonl_path = OUT_DIR / "comments_labeled.jsonl"
    csv_path = OUT_DIR / "comments_labeled.csv"
    write_jsonl(records, jsonl_path)
    write_csv(records, csv_path)
    print_stats(records, stats)
    print(f"\nwrote {len(records)} records:")
    print(f"  - {jsonl_path}")
    print(f"  - {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

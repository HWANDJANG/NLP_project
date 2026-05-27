"""Freeze a stratified train/val/test split so every experiment uses the same
partition and augmentation can never leak into val/test.

Reads:  data/labeled/comments_labeled.jsonl
Writes: data/labeled/split.json   {"train": [row_idx...], "val": [...], "test": [...]}

Row indices refer to the line order of comments_labeled.jsonl (0-based), counting
ONLY rows kept for training (comment non-empty, label in s/i/c). The split params
match src/classifier/klue_bert.py exactly (60/20/20, stratified, seed 42), so the
original (no-aug) KLUE-BERT numbers correspond to this same test set.

Usage:
    python -m src.augmentation.make_split
"""
from __future__ import annotations

import json
from pathlib import Path

from sklearn.model_selection import train_test_split

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LABELED = PROJECT_ROOT / "data" / "labeled" / "comments_labeled.jsonl"
SPLIT = PROJECT_ROOT / "data" / "labeled" / "split.json"
LABELS = ["s", "i", "c"]
SEED = 42


def load_indexed() -> tuple[list[int], list[str]]:
    """Return (row_index, label) for every training-eligible row, in file order."""
    idxs, labels = [], []
    for i, line in enumerate(LABELED.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        r = json.loads(line)
        comment = str(r.get("comment") or "").strip()
        label = r.get("label")
        if comment and label in LABELS:
            idxs.append(i)
            labels.append(label)
    return idxs, labels


def main() -> int:
    idxs, labels = load_indexed()
    # 60/20/20 — identical to klue_bert.py (test 0.20, then val 0.25 of the rest)
    tr_va_idx, te_idx, tr_va_lab, _ = train_test_split(
        idxs, labels, test_size=0.20, stratify=labels, random_state=SEED
    )
    tr_idx, va_idx = train_test_split(
        tr_va_idx, test_size=0.25, stratify=tr_va_lab, random_state=SEED
    )

    def dist(rows: list[int]) -> dict[str, int]:
        lab = [labels[idxs.index(i)] for i in rows]
        return {l: lab.count(l) for l in LABELS}

    split = {
        "train": sorted(tr_idx),
        "val": sorted(va_idx),
        "test": sorted(te_idx),
        "meta": {
            "seed": SEED,
            "source": LABELED.name,
            "train_dist": dist(tr_idx),
            "val_dist": dist(va_idx),
            "test_dist": dist(te_idx),
        },
    }
    SPLIT.write_text(json.dumps(split, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote {SPLIT}")
    print(f"  train={len(tr_idx)}  {split['meta']['train_dist']}")
    print(f"  val  ={len(va_idx)}  {split['meta']['val_dist']}")
    print(f"  test ={len(te_idx)}  {split['meta']['test_dist']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

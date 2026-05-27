"""2-class reformulations of the style classifier.

Same TF-IDF + LR pipeline as `baseline.py`, but tries two binary tasks:

  A) Critical vs Non-Critical            (c vs i+s)
  B) Subjective vs Informative           (s+c vs i)

These are easier than the 3-class problem and tell us whether the model
*has* enough signal to detect style direction, separately from whether
it can pick the right minority class.

Usage:
    python -m src.classifier.baseline_2class
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LABELED = PROJECT_ROOT / "data" / "labeled" / "comments_labeled.jsonl"
OUT = PROJECT_ROOT / "reports" / "classifier"


def load() -> tuple[list[str], list[str]]:
    X, y = [], []
    for line in LABELED.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        comment = str(r.get("comment") or "").strip()
        label = r.get("label")
        if comment and label in {"s", "i", "c"}:
            X.append(comment)
            y.append(label)
    return X, y


def build_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4),
            min_df=2, sublinear_tf=True, max_features=30000,
        )),
        ("clf", LogisticRegression(
            class_weight="balanced", max_iter=3000, solver="lbfgs",
        )),
    ])


def evaluate_binary(X: list[str], y: list[str], pos_label: str,
                    task_name: str, lines: list[str]) -> tuple[float, float]:
    """Run 5-fold CV + held-out test. Returns (mean macro-F1, mean positive-class F1)."""
    counts = {c: y.count(c) for c in sorted(set(y))}
    majority_acc = max(counts.values()) / len(y)
    header = f"\n{'=' * 64}\n{task_name}\n{'=' * 64}"
    print(header); lines.append(header)
    msg = (f"class counts: {counts}\n"
           f"majority baseline accuracy: {majority_acc:.3f}")
    print(msg); lines.append(msg)

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    macro, pos_f1 = [], []
    for fold, (tr, va) in enumerate(skf.split(X, y), 1):
        Xtr = [X[i] for i in tr]; ytr = [y[i] for i in tr]
        Xva = [X[i] for i in va]; yva = [y[i] for i in va]
        pipe = build_pipeline().fit(Xtr, ytr)
        pred = pipe.predict(Xva)
        macro.append(f1_score(yva, pred, average="macro"))
        pos_f1.append(f1_score(yva, pred, pos_label=pos_label, average="binary"))

    cv_msg = (f"5-fold CV macro-F1            : {np.mean(macro):.3f} ± {np.std(macro):.3f}\n"
              f"5-fold CV positive-class F1   : {np.mean(pos_f1):.3f} ± {np.std(pos_f1):.3f}"
              f"   (positive = {pos_label!r})")
    print(cv_msg); lines.append(cv_msg)

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.20, stratify=y, random_state=42)
    pipe = build_pipeline().fit(Xtr, ytr)
    pred = pipe.predict(Xte)
    report = classification_report(yte, pred, digits=3, zero_division=0)
    cm_labels = [pos_label, [c for c in counts if c != pos_label][0]]
    cm = confusion_matrix(yte, pred, labels=cm_labels)
    block = (f"\nHeld-out test (20%) classification report:\n{report}"
             f"Confusion matrix (rows=true, cols=pred, order={cm_labels}):\n{cm}")
    print(block); lines.append(block)

    return float(np.mean(macro)), float(np.mean(pos_f1))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    X, y3 = load()

    log_lines: list[str] = []
    intro = (f"Loaded {len(X)} comments. "
             f"3-class counts: s={y3.count('s')}, i={y3.count('i')}, c={y3.count('c')}")
    print(intro); log_lines.append(intro)

    # Task A: Critical vs Non-Critical
    yA = ["critical" if l == "c" else "non_critical" for l in y3]
    mA, pA = evaluate_binary(X, yA, pos_label="critical",
                             task_name="Task A) Critical vs Non-Critical (c vs i+s)",
                             lines=log_lines)

    # Task B: Subjective vs Informative
    yB = ["subjective" if l in {"s", "c"} else "informative" for l in y3]
    mB, pB = evaluate_binary(X, yB, pos_label="subjective",
                             task_name="Task B) Subjective vs Informative (s+c vs i)",
                             lines=log_lines)

    summary = (
        f"\n{'=' * 64}\n"
        f"Summary  (3-class baseline reference: macro-F1 = 0.568, accuracy = 0.835)\n"
        f"{'=' * 64}\n"
        f"  A. Critical vs Non-Critical : macro-F1={mA:.3f}   c-F1={pA:.3f}\n"
        f"  B. Subjective vs Informative: macro-F1={mB:.3f}   (s∪c)-F1={pB:.3f}"
    )
    print(summary); log_lines.append(summary)

    (OUT / "baseline_2class_metrics.txt").write_text("\n".join(log_lines), encoding="utf-8")
    print(f"\nartifact: {OUT / 'baseline_2class_metrics.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

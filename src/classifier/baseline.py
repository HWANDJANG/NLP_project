"""Baseline style classifier — TF-IDF (char n-gram) + Logistic Regression.

Reads:   data/labeled/comments_labeled.jsonl
Writes:  reports/classifier/baseline_metrics.txt
         reports/classifier/baseline_confusion.png
         reports/classifier/baseline_pipeline.joblib  (trained pipeline)

Design notes
------------
- Char n-grams (2~4) chosen over word n-grams because we have no Korean
  morpheme tokenizer in the loop; char_wb gives strong subword signal in
  Korean and handles agglutination naturally.
- `class_weight='balanced'` compensates for the heavy imbalance
  (i=2,038 / c=273 / s=82). Without it the model collapses to predicting i.
- 5-fold StratifiedKFold reports macro-F1 (mean ± std) for a stable read.
- Final report uses a held-out 20% split for the confusion matrix.

Usage:
    python -m src.classifier.baseline
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline


# -- Korean font for the confusion matrix labels ----------------------------
def _pick_korean_font() -> str | None:
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for n in ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"]:
        if n in installed:
            return n
    return None


_KF = _pick_korean_font()
if _KF:
    matplotlib.rcParams["font.family"] = _KF
matplotlib.rcParams["axes.unicode_minus"] = False


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LABELED = PROJECT_ROOT / "data" / "labeled" / "comments_labeled.jsonl"
OUT = PROJECT_ROOT / "reports" / "classifier"
LABEL_ORDER = ["s", "i", "c"]
LABEL_NAMES = {"s": "Supportive", "i": "Informative", "c": "Critical"}
TARGET_NAMES = [f"{l} · {LABEL_NAMES[l]}" for l in LABEL_ORDER]


def load_data() -> tuple[list[str], list[str]]:
    texts: list[str] = []
    labels: list[str] = []
    for line in LABELED.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        # Excel turns numeric-only comments (e.g. "123") into int; cast defensively.
        comment = str(r.get("comment") or "").strip()
        label = r.get("label")
        if comment and label in LABEL_ORDER:
            texts.append(comment)
            labels.append(label)
    return texts, labels


def build_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            min_df=2,
            sublinear_tf=True,
            max_features=30000,
        )),
        ("clf", LogisticRegression(
            class_weight="balanced",
            max_iter=3000,
            solver="lbfgs",   # supports native multiclass softmax
            C=1.0,
        )),
    ])


def cross_validate(X: list[str], y: list[str], seed: int = 42) -> tuple[list[float], list[float]]:
    """Return (per-fold macro-F1, per-fold weighted-F1)."""
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    macro, weighted = [], []
    for fold, (tr, va) in enumerate(skf.split(X, y), 1):
        Xtr, Xva = [X[i] for i in tr], [X[i] for i in va]
        ytr, yva = [y[i] for i in tr], [y[i] for i in va]
        pipe = build_pipeline().fit(Xtr, ytr)
        pred = pipe.predict(Xva)
        mf1 = f1_score(yva, pred, labels=LABEL_ORDER, average="macro")
        wf1 = f1_score(yva, pred, labels=LABEL_ORDER, average="weighted")
        macro.append(mf1); weighted.append(wf1)
        print(f"  fold {fold}: macro-F1={mf1:.3f}  weighted-F1={wf1:.3f}")
    return macro, weighted


def plot_confusion(cm: np.ndarray, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(LABEL_ORDER)))
    ax.set_yticks(range(len(LABEL_ORDER)))
    ax.set_xticklabels(TARGET_NAMES, rotation=20, ha="right")
    ax.set_yticklabels(TARGET_NAMES)
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    ax.set_title("Baseline confusion matrix (test 20%)")
    # cell text
    vmax = cm.max() if cm.size else 1
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            v = cm[i, j]
            ax.text(j, i, str(v), ha="center", va="center",
                    color="white" if v > vmax * 0.55 else "black", fontsize=11)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    X, y = load_data()
    print(f"loaded {len(X)} comments  (s={y.count('s')}, i={y.count('i')}, c={y.count('c')})\n")

    # 5-fold CV ----------------------------------------------------------
    print("5-fold stratified CV:")
    macro, weighted = cross_validate(X, y)
    print(f"\n  macro-F1   : {np.mean(macro):.3f} ± {np.std(macro):.3f}")
    print(f"  weighted-F1: {np.mean(weighted):.3f} ± {np.std(weighted):.3f}")

    # Final held-out evaluation ----------------------------------------
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.20, stratify=y, random_state=42
    )
    pipe = build_pipeline().fit(Xtr, ytr)
    pred = pipe.predict(Xte)

    print("\nHeld-out test (20%) classification report:")
    report = classification_report(
        yte, pred, labels=LABEL_ORDER, target_names=TARGET_NAMES, digits=3, zero_division=0
    )
    print(report)

    cm = confusion_matrix(yte, pred, labels=LABEL_ORDER)
    print("Confusion matrix (rows=true, cols=pred — order: s, i, c):")
    print(cm)

    # Persist artefacts ------------------------------------------------
    metrics_txt = OUT / "baseline_metrics.txt"
    metrics_txt.write_text(
        "TF-IDF (char_wb, 2-4) + Logistic Regression (class_weight=balanced)\n"
        f"\nDataset: {len(X)} comments (s={y.count('s')}, i={y.count('i')}, c={y.count('c')})\n"
        f"\n5-fold CV macro-F1   : {np.mean(macro):.3f} ± {np.std(macro):.3f}"
        f"\n5-fold CV weighted-F1: {np.mean(weighted):.3f} ± {np.std(weighted):.3f}\n"
        f"\nHeld-out test (20%) classification report:\n{report}\n"
        f"Confusion matrix (rows=true, cols=pred, order=s/i/c):\n{cm}\n",
        encoding="utf-8",
    )
    plot_confusion(cm, OUT / "baseline_confusion.png")
    joblib.dump(pipe, OUT / "baseline_pipeline.joblib")

    print(f"\nartifacts -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

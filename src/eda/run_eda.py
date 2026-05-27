"""EDA for the ssodam labeled dataset.

Reads:
    data/raw/{board}.jsonl              — posts with their comments
    data/labeled/comments_labeled.jsonl — flat comment×label records

Writes:
    reports/eda/01_counts_per_board.png
    reports/eda/02_label_share_per_board.png
    reports/eda/03_comment_length_per_board.png
    reports/eda/04_comments_per_post.png
    reports/eda/05_length_by_label.png
    Console: summary tables (per-board counts, label cross-tab, length stats).

Usage:
    python -m src.eda.run_eda
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager


def _pick_korean_font() -> str | None:
    """Return the first Korean font actually installed; None if nothing usable.

    Setting only an installed font avoids matplotlib's noisy "Font family X not
    found" spam when the fallback list contains unavailable names."""
    candidates = ["Malgun Gothic", "AppleGothic", "NanumGothic",
                  "NanumBarunGothic", "Noto Sans CJK KR", "Gulim", "Batang"]
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in installed:
            return name
    return None


_KFONT = _pick_korean_font()
if _KFONT:
    matplotlib.rcParams["font.family"] = _KFONT
else:
    print("[warn] no Korean font found — chart labels will show as boxes.")
matplotlib.rcParams["axes.unicode_minus"] = False

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
LABELED = PROJECT_ROOT / "data" / "labeled" / "comments_labeled.jsonl"
OUT = PROJECT_ROOT / "reports" / "eda"

BOARD_ORDER = ["익게2", "연애상담소", "정치", "취업게시판"]
LABEL_ORDER = ["s", "i", "c"]
LABEL_NAMES = {"s": "Supportive", "i": "Informative", "c": "Critical"}
# Soft blue / neutral grey / warm red — keeps the semantic ordering visible.
LABEL_COLORS = {"s": "#5dade2", "i": "#aab7b8", "c": "#e74c3c"}


def load_posts() -> pd.DataFrame:
    rows = []
    for p in sorted(RAW_DIR.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return pd.DataFrame(rows)


def load_labeled() -> pd.DataFrame:
    rows = []
    for line in LABELED.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    # Some xlsx rows came through with NaN comment; treat as empty string so
    # str.len() returns 0 instead of NaN (which silently breaks boxplots).
    df["comment_len"] = df["comment"].fillna("").astype(str).str.len()
    return df


def board_summary(posts: pd.DataFrame, labeled: pd.DataFrame) -> pd.DataFrame:
    s = pd.DataFrame({
        "posts": posts.groupby("board").size(),
        "raw_comments": posts.groupby("board")["comment_count"].sum(),
        "labeled_kept": labeled.groupby("board").size(),
    }).reindex(BOARD_ORDER)
    s["avg_comments_per_post"] = (s["raw_comments"] / s["posts"]).round(2)
    return s


def chart_counts(summary: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = range(len(BOARD_ORDER))
    w = 0.4
    ax.bar([i - w / 2 for i in x], summary["posts"], w, color="#34495e", label="게시글 수")
    ax.bar([i + w / 2 for i in x], summary["labeled_kept"], w, color="#5dade2", label="라벨링된 댓글 수")
    for i, v in enumerate(summary["posts"]):
        ax.text(i - w / 2, v + 8, str(v), ha="center", fontsize=9)
    for i, v in enumerate(summary["labeled_kept"]):
        ax.text(i + w / 2, v + 8, str(v), ha="center", fontsize=9)
    ax.set_xticks(list(x))
    ax.set_xticklabels(BOARD_ORDER)
    ax.set_ylabel("count")
    ax.set_title("게시판별 게시글 / 라벨링 댓글 수")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "01_counts_per_board.png", dpi=120)
    plt.close(fig)


def chart_label_share(labeled: pd.DataFrame) -> pd.DataFrame:
    cross_n = pd.crosstab(labeled["board"], labeled["label"]).reindex(
        index=BOARD_ORDER, columns=LABEL_ORDER, fill_value=0
    )
    cross_pct = (cross_n.div(cross_n.sum(axis=1), axis=0) * 100).round(1)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bottom = [0.0] * len(BOARD_ORDER)
    for lab in LABEL_ORDER:
        vals = cross_pct[lab].tolist()
        ax.bar(BOARD_ORDER, vals, bottom=bottom, color=LABEL_COLORS[lab],
               label=f"{lab} · {LABEL_NAMES[lab]}", edgecolor="white")
        for i, v in enumerate(vals):
            if v > 2.5:
                ax.text(i, bottom[i] + v / 2, f"{v:.1f}%",
                        ha="center", va="center", color="white", fontsize=9, fontweight="bold")
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_ylim(0, 100)
    ax.set_ylabel("비율 (%)")
    ax.set_title("게시판별 댓글 스타일 분포")
    ax.legend(loc="upper left", framealpha=0.95, bbox_to_anchor=(1.01, 1.0))
    fig.tight_layout()
    fig.savefig(OUT / "02_label_share_per_board.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return cross_n


def chart_comment_length_board(labeled: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    data = [labeled.loc[labeled["board"] == b, "comment_len"].values for b in BOARD_ORDER]
    bp = ax.boxplot(data, tick_labels=BOARD_ORDER, showfliers=False, patch_artist=True)
    for patch in bp["boxes"]:
        patch.set_facecolor("#85c1e9")
    ax.set_ylabel("댓글 길이 (글자수)")
    ax.set_title("게시판별 댓글 길이 분포 (이상치 제외)")
    fig.tight_layout()
    fig.savefig(OUT / "03_comment_length_per_board.png", dpi=120)
    plt.close(fig)


def chart_comments_per_post(posts: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bins = list(range(3, 12))
    for b in BOARD_ORDER:
        v = posts.loc[posts["board"] == b, "comment_count"]
        ax.hist(v, bins=bins, alpha=0.55, label=b, edgecolor="white")
    ax.set_xlabel("게시글당 댓글 수 (필터 후)")
    ax.set_ylabel("게시글 수")
    ax.set_title("게시판별 게시글당 댓글 수 분포")
    ax.set_xticks(bins[:-1])
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "04_comments_per_post.png", dpi=120)
    plt.close(fig)


def chart_length_by_label(labeled: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7, 4.5))
    data = [labeled.loc[labeled["label"] == l, "comment_len"].values for l in LABEL_ORDER]
    labels = [f"{l}\n{LABEL_NAMES[l]}\n(n={len(d)})" for l, d in zip(LABEL_ORDER, data)]
    bp = ax.boxplot(data, tick_labels=labels, showfliers=False, patch_artist=True)
    for patch, lab in zip(bp["boxes"], LABEL_ORDER):
        patch.set_facecolor(LABEL_COLORS[lab])
    ax.set_ylabel("댓글 길이 (글자수)")
    ax.set_title("라벨별 댓글 길이 분포")
    fig.tight_layout()
    fig.savefig(OUT / "05_length_by_label.png", dpi=120)
    plt.close(fig)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    posts = load_posts()
    labeled = load_labeled()

    # ---- console tables ----
    pd.options.display.width = 120
    pd.options.display.max_columns = 12

    print("=" * 60)
    print("1) 게시판별 게시글·댓글 요약")
    print("=" * 60)
    summary = board_summary(posts, labeled)
    print(summary)

    print("\n" + "=" * 60)
    print("2) 게시판 × 라벨 (개수)")
    print("=" * 60)
    cross_n = pd.crosstab(labeled["board"], labeled["label"]).reindex(
        index=BOARD_ORDER, columns=LABEL_ORDER, fill_value=0
    )
    cross_n["total"] = cross_n.sum(axis=1)
    print(cross_n)

    print("\n" + "=" * 60)
    print("3) 게시판 × 라벨 (비율 %)")
    print("=" * 60)
    cross_pct = (cross_n[LABEL_ORDER].div(cross_n["total"], axis=0) * 100).round(1)
    print(cross_pct)

    print("\n" + "=" * 60)
    print("4) 댓글 길이 통계 (글자수)")
    print("=" * 60)
    len_stats = labeled.groupby("board")["comment_len"].describe()[["count", "mean", "50%", "max"]]
    len_stats.columns = ["count", "mean", "median", "max"]
    len_stats = len_stats.reindex(BOARD_ORDER).round(1)
    print(len_stats)

    print("\n   라벨별 평균 길이:")
    print(labeled.groupby("label")["comment_len"].describe()[["count", "mean", "50%"]]
          .reindex(LABEL_ORDER).round(1).rename(columns={"50%": "median"}))

    # ---- charts ----
    chart_counts(summary)
    chart_label_share(labeled)
    chart_comment_length_board(labeled)
    chart_comments_per_post(posts)
    chart_length_by_label(labeled)
    print(f"\n[charts] saved 5 PNGs -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

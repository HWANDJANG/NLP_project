"""Augment the TRAIN split's s/c comments with Gemini paraphrases.

Reads:  data/labeled/comments_labeled.jsonl
        data/labeled/split.json          (train indices)
Writes: data/labeled/train_augment_only.jsonl   (generated paraphrases only)

Each output record:
    {"comment", "label", "label_name", "board",
     "augmented": true, "source_index": <row idx in comments_labeled.jsonl>}

Guarantees
----------
- Only TRAIN rows are touched (val/test never read here).
- Only s and c are augmented (i is already abundant).
- Paraphrases inherit the source label; the prompt asks Gemini to preserve
  emotion / tone / intensity so the label stays valid.
- Resumable: already-augmented source_index values are skipped, so re-running
  after an interruption continues where it stopped.

Usage:
    python -m src.augmentation.augment_gemini                 # s×3, c×2 (default)
    python -m src.augmentation.augment_gemini --n-s 4 --n-c 2
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LABELED = PROJECT_ROOT / "data" / "labeled" / "comments_labeled.jsonl"
SPLIT = PROJECT_ROOT / "data" / "labeled" / "split.json"
OUT = PROJECT_ROOT / "data" / "labeled" / "train_augment_only.jsonl"

MODEL = "gemini-2.5-flash"
REQUEST_SLEEP = 4.0     # ~15 requests/min — safe for the free tier
MAX_RETRIES = 5
MIN_CHARS = 5

LABEL_NAMES = {"s": "Supportive", "i": "Informative", "c": "Critical"}
STYLE_DESC = {
    "s": "공감·위로·응원·정서적 지지가 담긴 따뜻한 말투",
    "c": "공격·조롱·비난·냉소가 담긴 날선 말투",
}

PROMPT_TMPL = (
    "너는 한국어 온라인 커뮤니티(대학 익명 게시판) 댓글 데이터를 늘리는 도구야.\n"
    "아래 '원본 댓글'과 **같은 의도·감정·강도·말투**를 유지하되 표현만 다른 댓글 {n}개를 만들어.\n\n"
    "규칙:\n"
    "- 반드시 유지할 스타일: {style}\n"
    "- 인터넷 구어체, 반말/줄임말 등 원본의 결을 그대로 살릴 것\n"
    "- 길이감도 원본과 비슷하게\n"
    "- 새로운 정보나 다른 감정(반대 톤)으로 바꾸지 말 것\n"
    "- 설명·번호·따옴표 없이, 한 줄에 하나씩 댓글만 출력\n\n"
    "원본 댓글: {comment}"
)


def load_train_targets() -> list[tuple[int, dict]]:
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    train_idx = set(split["train"])
    lines = LABELED.read_text(encoding="utf-8").splitlines()
    targets = []
    for i, line in enumerate(lines):
        if i not in train_idx or not line.strip():
            continue
        r = json.loads(line)
        if r.get("label") in ("s", "c"):
            targets.append((i, r))
    return targets


def load_done() -> set[int]:
    if not OUT.exists():
        return set()
    done = set()
    for line in OUT.read_text(encoding="utf-8").splitlines():
        if line.strip():
            done.add(json.loads(line)["source_index"])
    return done


def generate(client: genai.Client, comment: str, label: str, n: int) -> list[str]:
    prompt = PROMPT_TMPL.format(n=n, style=STYLE_DESC[label], comment=comment)
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.models.generate_content(model=MODEL, contents=prompt)
            text = resp.text or ""
            lines = [l.strip(" \t-•\"'") for l in text.splitlines()]
            out = []
            for l in lines:
                if len(l) >= MIN_CHARS and l != comment.strip():
                    out.append(l)
            return out[:n]
        except Exception as e:
            wait = REQUEST_SLEEP * (2 ** attempt)
            msg = str(e)[:100]
            print(f"    retry {attempt + 1}/{MAX_RETRIES} after {wait:.0f}s ({msg})")
            time.sleep(wait)
    print("    giving up on this comment")
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-s", type=int, default=3, help="paraphrases per Supportive comment")
    ap.add_argument("--n-c", type=int, default=2, help="paraphrases per Critical comment")
    args = ap.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY not set in .env")
    client = genai.Client(api_key=api_key)

    targets = load_train_targets()
    done = load_done()
    todo = [(i, r) for i, r in targets if i not in done]
    n_per = {"s": args.n_s, "c": args.n_c}

    print(f"train s/c targets: {len(targets)}  (already done: {len(done)}, to do: {len(todo)})")
    print(f"paraphrases per comment: s={args.n_s}, c={args.n_c}")
    est = len(todo) * REQUEST_SLEEP / 60
    print(f"estimated time: ~{est:.0f} min\n")

    generated = 0
    with OUT.open("a", encoding="utf-8") as f:
        for k, (idx, r) in enumerate(todo, 1):
            label = r["label"]
            comment = str(r.get("comment") or "").strip()
            paras = generate(client, comment, label, n_per[label])
            for p in paras:
                rec = {
                    "comment": p,
                    "label": label,
                    "label_name": LABEL_NAMES[label],
                    "board": r.get("board"),
                    "augmented": True,
                    "source_index": idx,
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                generated += 1
            f.flush()
            if k % 10 == 0 or k == len(todo):
                print(f"  [{k}/{len(todo)}] {label} src={idx} -> +{len(paras)} "
                      f"(total generated this run: {generated})")
            time.sleep(REQUEST_SLEEP)

    # final tally
    total = 0
    counts = {"s": 0, "c": 0}
    for line in OUT.read_text(encoding="utf-8").splitlines():
        if line.strip():
            counts[json.loads(line)["label"]] += 1
            total += 1
    print(f"\ndone. {OUT.name}: {total} augmented rows (s={counts['s']}, c={counts['c']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

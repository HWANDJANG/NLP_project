"""KLUE-BERT fine-tuned 3-class style classifier (s / i / c).

Reads:  data/labeled/comments_labeled.jsonl
Writes: reports/classifier/klue_bert_metrics.txt
        reports/classifier/klue_bert_confusion.png
        reports/classifier/klue_bert/      (HF model + tokenizer)

Design notes
------------
- Backbone: `klue/bert-base` (110M params, Korean BPE). First run downloads
  ~440MB into the HF cache.
- CPU training is intentional — MX250 has only 2GB VRAM, which OOMs on
  BERT-base with normal batch sizes. On CPU expect ~30–60 min for 4 epochs
  over 1,436 train examples.
- Class imbalance handled via inverse-frequency weighted CE loss
  (subclassed `Trainer.compute_loss`). `class_weight='balanced'` from the
  baseline is the rough analogue.
- max_length=96 covers 95%+ of comments (p90=81 chars ≈ 60 BPE tokens).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from matplotlib import font_manager
import matplotlib
import matplotlib.pyplot as plt
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
    set_seed,
)


# ---------------- config ----------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LABELED = PROJECT_ROOT / "data" / "labeled" / "comments_labeled.jsonl"
SPLIT = PROJECT_ROOT / "data" / "labeled" / "split.json"
AUGMENT = PROJECT_ROOT / "data" / "labeled" / "train_augment_only.jsonl"
OUT = PROJECT_ROOT / "reports" / "classifier"
MODEL_OUT = OUT / "klue_bert"

MODEL_NAME = "klue/bert-base"
SEED = 42
MAX_LEN = 96
EPOCHS = 4
BATCH_TRAIN = 16
BATCH_EVAL = 32
LR = 2e-5
WEIGHT_DECAY = 0.01

LABELS = ["s", "i", "c"]
LABEL2ID = {l: i for i, l in enumerate(LABELS)}
ID2LABEL = {i: l for l, i in LABEL2ID.items()}
PRETTY = {"s": "Supportive", "i": "Informative", "c": "Critical"}


# ---------------- korean font for confusion matrix ----------------
def _pick_kfont() -> str | None:
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for n in ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"]:
        if n in installed:
            return n
    return None


_KF = _pick_kfont()
if _KF:
    matplotlib.rcParams["font.family"] = _KF
matplotlib.rcParams["axes.unicode_minus"] = False


# ---------------- dataset ----------------
class CommentDataset(Dataset):
    def __init__(self, encodings, labels):
        self.encodings = encodings
        self.labels = labels

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, idx):
        item = {k: v[idx] for k, v in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx], dtype=torch.long)
        return item


def _records_by_index() -> dict[int, dict]:
    out = {}
    for i, line in enumerate(LABELED.read_text(encoding="utf-8").splitlines()):
        if line.strip():
            out[i] = json.loads(line)
    return out


def load_split_xy(use_augmented: bool):
    """Load train/val/test from the frozen split.json.

    When use_augmented=True, append the Gemini paraphrases (train only) to the
    training set. val/test always come from the original real comments.
    Returns (X_tr, y_tr, X_va, y_va, X_te, y_te).
    """
    if not SPLIT.exists():
        raise SystemExit(f"missing {SPLIT} — run `python -m src.augmentation.make_split` first")
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    recs = _records_by_index()

    def to_xy(indices: list[int]):
        X, y = [], []
        for i in indices:
            r = recs[i]
            X.append(str(r.get("comment") or "").strip())
            y.append(LABEL2ID[r["label"]])
        return X, y

    X_tr, y_tr = to_xy(split["train"])
    X_va, y_va = to_xy(split["val"])
    X_te, y_te = to_xy(split["test"])

    if use_augmented:
        if not AUGMENT.exists():
            raise SystemExit(f"missing {AUGMENT} — run `python -m src.augmentation.augment_gemini` first")
        n_aug = 0
        for line in AUGMENT.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            comment = str(r.get("comment") or "").strip()
            if comment and r.get("label") in LABEL2ID:
                X_tr.append(comment)
                y_tr.append(LABEL2ID[r["label"]])
                n_aug += 1
        print(f"augmented train with {n_aug} paraphrases")

    return X_tr, y_tr, X_va, y_va, X_te, y_te


# ---------------- weighted trainer ----------------
class WeightedTrainer(Trainer):
    """Trainer with class-weighted cross-entropy. Compensates for s=82 vs i=2,038."""

    def __init__(self, class_weights: torch.Tensor, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.class_weights = class_weights

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        loss = torch.nn.functional.cross_entropy(
            outputs.logits, labels, weight=self.class_weights.to(outputs.logits.device)
        )
        return (loss, outputs) if return_outputs else loss


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    pred = np.argmax(logits, axis=-1)
    return {
        "macro_f1": f1_score(labels, pred, average="macro"),
        "weighted_f1": f1_score(labels, pred, average="weighted"),
    }


# ---------------- confusion matrix png ----------------
def plot_confusion(cm: np.ndarray, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    im = ax.imshow(cm, cmap="Blues")
    names = [f"{l} · {PRETTY[l]}" for l in LABELS]
    ax.set_xticks(range(len(LABELS))); ax.set_yticks(range(len(LABELS)))
    ax.set_xticklabels(names, rotation=20, ha="right"); ax.set_yticklabels(names)
    ax.set_xlabel("predicted"); ax.set_ylabel("true")
    ax.set_title("KLUE-BERT confusion matrix (test 20%)")
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


# ---------------- main ----------------
def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="KLUE-BERT style classifier")
    ap.add_argument("--augmented", action="store_true",
                    help="add Gemini paraphrases to the training set (val/test stay original)")
    cli = ap.parse_args()
    suffix = "_aug" if cli.augmented else ""

    OUT.mkdir(parents=True, exist_ok=True)
    set_seed(SEED)

    X_tr, y_tr, X_va, y_va, X_te, y_te = load_split_xy(cli.augmented)
    print(f"split: train={len(X_tr)}  val={len(X_va)}  test={len(X_te)}  "
          f"(augmented={cli.augmented})")
    print(f"train label dist: s={y_tr.count(0)} i={y_tr.count(1)} c={y_tr.count(2)}")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    def encode(texts):
        return tokenizer(texts, truncation=True, padding=True,
                         max_length=MAX_LEN, return_tensors="pt")

    ds_tr = CommentDataset(encode(X_tr), y_tr)
    ds_va = CommentDataset(encode(X_va), y_va)
    ds_te = CommentDataset(encode(X_te), y_te)

    counts = np.array([y_tr.count(i) for i in range(len(LABELS))], dtype=np.float32)
    class_weights = torch.tensor(len(y_tr) / (len(LABELS) * counts), dtype=torch.float32)
    print(f"class weights: {dict(zip(LABELS, class_weights.tolist()))}")

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, num_labels=len(LABELS),
        id2label=ID2LABEL, label2id=LABEL2ID,
    )

    args = TrainingArguments(
        output_dir=str(MODEL_OUT) + suffix + "/_trainer_state",
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH_TRAIN,
        per_device_eval_batch_size=BATCH_EVAL,
        learning_rate=LR,
        weight_decay=WEIGHT_DECAY,
        warmup_ratio=0.1,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="macro_f1",
        greater_is_better=True,
        save_total_limit=1,
        logging_steps=50,
        report_to=[],
        seed=SEED,
        use_cpu=True,
    )

    trainer = WeightedTrainer(
        class_weights=class_weights,
        model=model, args=args,
        train_dataset=ds_tr, eval_dataset=ds_va,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    trainer.train()

    # Persist best model for re-use
    model_dir = Path(str(MODEL_OUT) + suffix)
    model_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(model_dir))
    tokenizer.save_pretrained(str(model_dir))

    # ---- final test evaluation (original real comments only) ----
    pred_logits = trainer.predict(ds_te).predictions
    y_pred = np.argmax(pred_logits, axis=-1).tolist()
    yt_l = [ID2LABEL[i] for i in y_te]
    yp_l = [ID2LABEL[i] for i in y_pred]

    target_names = [f"{l} · {PRETTY[l]}" for l in LABELS]
    report = classification_report(
        yt_l, yp_l, labels=LABELS, target_names=target_names, digits=3, zero_division=0
    )
    cm = confusion_matrix(yt_l, yp_l, labels=LABELS)

    print("\nHeld-out test classification report:")
    print(report)
    print("Confusion matrix (rows=true, cols=pred, order=s/i/c):")
    print(cm)

    tag = "augmented (train += Gemini paraphrases)" if cli.augmented else "original train only"
    (OUT / f"klue_bert{suffix}_metrics.txt").write_text(
        f"KLUE-BERT ({MODEL_NAME}) fine-tuning — {tag}\n"
        f"epochs={EPOCHS} batch={BATCH_TRAIN} lr={LR} max_len={MAX_LEN} "
        f"class-weighted CE | split.json (60/20/20)\n\n"
        f"train={len(X_tr)} (s={y_tr.count(0)} i={y_tr.count(1)} c={y_tr.count(2)}) "
        f"| val={len(X_va)} | test={len(X_te)}\n"
        f"** val/test are ORIGINAL real comments only **\n\n"
        f"Held-out test classification report:\n{report}\n"
        f"Confusion matrix (rows=true, cols=pred, order=s/i/c):\n{cm}\n",
        encoding="utf-8",
    )
    plot_confusion(cm, OUT / f"klue_bert{suffix}_confusion.png")
    print(f"\nartifacts -> {OUT} (suffix={suffix or 'none'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

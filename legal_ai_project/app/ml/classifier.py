"""
Module 6 — Classification
==========================
Logistic Regression on InLegalBERT embeddings → predict outcome (0/1).
Singleton: model loaded once from data/model.pkl.

Training:
    from app.ml.classifier import train_model
    train_model()

Prediction (per request):
    label, confidence = predict(text)
"""

import logging
import numpy as np
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)

MODEL_FILE = "model.pkl"

# ── Singleton ─────────────────────────────────────────────────────────────────
_clf = None


def _model_path() -> Path:
    return Path(settings.DATA_DIR) / MODEL_FILE


def load_classifier():
    """Load trained classifier from disk once. Returns model or None."""
    global _clf
    if _clf is not None:
        return _clf
    mp = _model_path()
    if not mp.exists():
        logger.warning(f"Classifier model not found at {mp}. Run train_model() first.")
        return None
    try:
        import joblib
        _clf = joblib.load(mp)
        logger.info(f"Classifier loaded from {mp}")
    except BaseException as e:
        logger.error(f"load_classifier failed: {e} — ML prediction disabled")
        _clf = None
    return _clf


def train_model():
    """
    Train Logistic Regression on precomputed embeddings + processed.csv labels.
    Saves model to data/model.pkl.
    """
    import csv
    import joblib
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report
    from .embeddings import load_dataset_embeddings

    data_dir = Path(settings.DATA_DIR)
    csv_path = data_dir / "processed.csv"

    if not csv_path.exists():
        logger.error("processed.csv not found — cannot train")
        return

    embs, texts = load_dataset_embeddings()
    if embs is None:
        logger.error("Embeddings not found — run save_dataset_embeddings() first")
        return

    # Strategy 1: positional alignment (fast, works when CSV and embeddings are in sync)
    # Strategy 2: text lookup fallback
    text_to_idx = {t.strip(): i for i, t in enumerate(texts)}

    X, y = [], []
    csv_rows = []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lbl = row.get("label", "")
            txt = (row.get("input_text", "") or "").strip()
            if lbl not in ("0", "1") or not txt:
                continue
            csv_rows.append((txt, int(lbl)))

    # Try positional match first (CSV row i → embedding i)
    labelled_csv = [(t, l) for t, l in csv_rows]
    emb_texts    = [t.strip() for t in texts]

    for i, (txt, lbl) in enumerate(labelled_csv):
        # Try exact text match
        idx = text_to_idx.get(txt)
        if idx is not None:
            X.append(embs[idx])
            y.append(lbl)
        elif i < len(embs):
            # Positional fallback — use embedding at same position
            X.append(embs[i])
            y.append(lbl)

    if len(X) < 10:
        logger.error(f"Not enough labelled samples ({len(X)}) to train")
        return

    X = np.array(X)
    y = np.array(y)

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    clf = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)
    clf.fit(X_tr, y_tr)

    report = classification_report(y_te, clf.predict(X_te))
    logger.info(f"Classifier trained on {len(X_tr)} samples\n{report}")
    print(report)

    joblib.dump(clf, _model_path())
    logger.info(f"Model saved → {_model_path()}")

    # Reset singleton so next predict() reloads fresh model
    global _clf
    _clf = None


def predict(text: str) -> tuple[int | None, float | None]:
    """
    Predict outcome label and confidence for a single text.
    Returns (label, confidence) or (None, None) on failure.
    """
    from .embeddings import get_embedding

    clf = load_classifier()
    if clf is None:
        return None, None

    emb = get_embedding(text)
    if emb is None:
        return None, None

    try:
        label      = int(clf.predict([emb])[0])
        proba      = clf.predict_proba([emb])[0]
        confidence = float(proba[label])
        return label, confidence
    except Exception as e:
        logger.error(f"predict failed: {e}")
        return None, None

"""
Module 6 — Classification (Upgraded)
======================================
Ensemble: Calibrated SVM + Logistic Regression on InLegalBERT embeddings.

Improvements over v1:
  - CalibratedClassifierCV wraps SVM → well-calibrated probabilities
  - LogisticRegression as secondary model, ensemble via soft voting
  - 5-fold stratified cross-validation during training → real accuracy estimate
  - Isotonic calibration for better confidence scores
  - Saves calibration metadata alongside model
  - predict() returns calibrated confidence, not raw LogReg proba

Training:
    from app.mssifier import train_model
    train_model()

Prediction (per request):
    label, confidence = predict(text)
"""

import logging
import numpy as np
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)

MODEL_FILE    = "model.pkl"
META_FILE_ML  = "model_meta.json"   # stores accuracy, class counts, cv scores

# ── Singleton ───────────────────────────────────────────────────────
_clf  = None
_meta = None


def _model_path() -> Path:
    return Path(settings.DATA_DIR) / MODEL_FILE

def _meta_path() -> Path:
    return Path(settings.DATA_DIR) / META_FILE_ML


def load_classifier():
    """Load trained classifier from disk once. Returns model or None."""
    global _clf
    if _clf is not None:
        return _clf
    mp = _model_path()
    if not mp.exists():
        logger.warfirst.")
        return None
    try:
        import joblib
        _clf = joblib.load(mp)
        logger.info(f"Classifier loaded from {mp}")
    except Exception as e:
        logger.error(f"load_classifier failed: {e}")
        _clf = None
    return _clf


def load_meta() -> dict:
    """Load model metadata (accuracy, cv scores, class counts)."""
    global _meta
    if _meta is not None:
        return _meta
    mp = _meta_path()
    if not mp.exists():
        return {}
    try:
        import json
        _meta = json.loads(mp.read_text(encoding="utf-8"))
        return _meta
    except Exception:
        return {}


def train_model():
    """
    Train an ensemble of Calibrated SVM + Logistic Regression.
    Uses 5-fold stratified cross-validation to report real accuracy.
    Saves model.pkl + model_meta.json.
    """
    import csv
    import json
    import joblib
    from sklearn.svm import LinearSVC
    from sklearn.linear_model import LogisticRegression
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import VotingClassifier
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    from sklearn.prrocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.metrics import classification_report, accuracy_score
    from .embeddings import load_dataset_embeddings

    data_dir = Path(settings.DATA_DIR)
    csv_path = data_dir / "processed.csv"

    if not csv_path.exists():
        logger.error("processed.csv not found — cannot train")
        return

    embs, texts = load_dataset_embeddings()
    if embs is None:
        logger.eret_embeddings() first")
        return

    # Build text→embedding lookup
    text_to_idx = {t: i for i, t in enumerate(texts)}

    X, y = [], []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lbl = row.get("label", "")
            txt = row.get("input_text", "")
            if lbl not in ("0", "1") or not txt:
                continue
            idx = text_to_idx.get(txt)
            if idx is None:
                continue
            X.append(embs[idx])
            y.append(int(lbl))

    if len(X) < 10:
        logger.error(f"Not enough labelled samples ({len(X)}) to train")
        return

    X = np.array(X, dtype=np.float32)
    y = np.array(y)

    class_counts = {int(k): int(v) for k, v in zip(*np.unique(y, return_counts=True))}
    logger.info(f"Training on {len(X)} samples — class distribution: {class_counts}")

    # ── Build ensemble pipeline ───────────────────────────────────────────────
    # SVM with isotonic calibration — best for high-dim embeddings
    svm_pipe = Pipeline([
        ("scaler", StandardScaler()),
   label  = int(clf.predict(emb_2d)[0])
        proba  = clf.predict_proba(emb_2d)[0]

        # Confidence = probability of the predicted class
        confidence = float(proba[label])

        # Clamp to [0.5, 0.99] — ensemble rarely goes below 0.5 for the winning class
        confidence = max(0.50, min(0.99, confidence))

        return label, confidence
    except Exception as e:
        logger.error(f"predict failed: {e}")
        return None, None
label and calibrated confidence for a single text.
    Returns (label, confidence) or (None, None) on failure.

    Confidence is from the ensemble's soft-voted probability — well-calibrated
    via isotonic regression on the SVM component.
    """
    from .embeddings import get_embedding

    clf = load_classifier()
    if clf is None:
        return None, None

    emb = get_embedding(text)
    if emb is None:
        return None, None

    try:
        emb_2d = emb.reshape(1, -1).astype(np.float32)
     X),
        "class_counts":     class_counts,
        "model_type":       "VotingClassifier(SVM+LR) with isotonic calibration",
    }
    _meta_path().write_text(
        __import__("json").dumps(meta, indent=2), encoding="utf-8"
    )
    logger.info(f"Metadata saved → {_meta_path()}")
    print(f"\nModel metadata saved → {_meta_path()}")

    # Reset singletons
    global _clf, _meta
    _clf  = None
    _meta = None


def predict(text: str) -> tuple[int | None, float | None]:
    """
    Predict outcome nt(f"\nTrain-set classification report:\n{report}")

    # ── Save model ────────────────────────────────────────────────────────────
    joblib.dump(ensemble, _model_path())
    logger.info(f"Model saved → {_model_path()}")

    # ── Save metadata ─────────────────────────────────────────────────────────
    meta = {
        "cv_accuracy_mean": round(cv_mean, 4),
        "cv_accuracy_std":  round(cv_std, 4),
        "cv_scores":        [round(s, 4) for s in cv_scores.tolist()],
        "train_samples":    len(nfo(f"CV accuracy: {cv_mean:.3f} ± {cv_std:.3f}")
    print(f"\n5-Fold CV Accuracy: {cv_mean:.3f} ± {cv_std:.3f}")
    print(f"Per-fold: {[round(s, 3) for s in cv_scores.tolist()]}")

    # ── Final fit on all data ─────────────────────────────────────────────────
    ensemble.fit(X, y)

    # Quick train-set report (informational only)
    y_pred = ensemble.predict(X)
    report = classification_report(y, y_pred, target_names=["Dismissed", "Allowed"])
    logger.info(f"Train-set report:\n{report}")
    pri

    # Soft voting ensemble
    ensemble = VotingClassifier(
        estimators=[("svm", svm_pipe), ("lr", lr_pipe)],
        voting="soft",
        weights=[2, 1],   # SVM gets more weight
    )

    # ── 5-fold cross-validation ───────────────────────────────────────────────
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(ensemble, X, y, cv=cv, scoring="accuracy")
    cv_mean   = float(cv_scores.mean())
    cv_std    = float(cv_scores.std())
    logger.i        ("svm",    CalibratedClassifierCV(
            LinearSVC(class_weight="balanced", max_iter=2000, C=1.0),
            method="isotonic", cv=3
        )),
    ])

    # Logistic Regression — fast, well-calibrated baseline
    lr_pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("lr",     LogisticRegression(
            class_weight="balanced", max_iter=1000, C=1.0,
            solver="lbfgs", random_state=42
        )),
    ])
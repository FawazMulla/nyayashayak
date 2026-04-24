"""
Module 6 — Classification (Upgraded)
======================================
Ensemble: Calibrated SVM + Logistic Regression on InLegalBERT embeddings.

Improvements over v1:
  - CalibratedClassifierCV wraps SVM -> well-calibrated probabilities
  - LogisticRegression as secondary model, ensemble via soft voting
  - 5-fold stratified cross-validation -> real accuracy estimate
  - Saves model_meta.json with cv scores, class counts, model type

Training:
    python manage.py build_ml

Prediction:
    label, confidence = predict(text)
"""

import logging
import numpy as np
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)

MODEL_FILE   = "model.pkl"
META_FILE_ML = "model_meta.json"

_clf  = None
_meta = None


def _model_path() -> Path:
    return Path(settings.DATA_DIR) / MODEL_FILE


def _meta_path() -> Path:
    return Path(settings.DATA_DIR) / META_FILE_ML


def load_classifier():
    global _clf
    if _clf is not None:
        return _clf
    mp = _model_path()
    if not mp.exists():
        logger.warning(f"Classifier not found at {mp}. Run build_ml first.")
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
    Train Calibrated SVM + LR ensemble with 5-fold CV.
    Saves model.pkl + model_meta.json to data/.
    """
    import csv
    import json
    import joblib
    from sklearn.svm import LinearSVC
    from sklearn.linear_model import LogisticRegression
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import VotingClassifier
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.metrics import classification_report
    from .embeddings import load_dataset_embeddings

    data_dir = Path(settings.DATA_DIR)
    csv_path = data_dir / "processed.csv"

    if not csv_path.exists():
        logger.error("processed.csv not found")
        return

    embs, texts = load_dataset_embeddings()
    if embs is None:
        logger.error("Embeddings not found — run build_ml --embed-only first")
        return

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
        logger.error(f"Not enough samples ({len(X)}) to train")
        return

    X = np.array(X, dtype=np.float32)
    y = np.array(y)

    class_counts = {int(k): int(v) for k, v in zip(*np.unique(y, return_counts=True))}
    logger.info(f"Training on {len(X)} samples — {class_counts}")
    print(f"Training on {len(X)} samples — class distribution: {class_counts}")

    # Calibrated SVM (isotonic) — best for high-dim embeddings
    svm_pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("svm", CalibratedClassifierCV(
            LinearSVC(class_weight="balanced", max_iter=5000, C=1.0),
            method="isotonic", cv=3
        )),
    ])

    # Logistic Regression baseline
    lr_pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(
            class_weight="balanced", max_iter=1000, C=1.0,
            solver="lbfgs", random_state=42
        )),
    ])

    # Soft-voting ensemble — SVM weighted 2x
    ensemble = VotingClassifier(
        estimators=[("svm", svm_pipe), ("lr", lr_pipe)],
        voting="soft",
        weights=[2, 1],
    )

    # 5-fold stratified CV
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(ensemble, X, y, cv=cv, scoring="accuracy")
    cv_mean = float(cv_scores.mean())
    cv_std  = float(cv_scores.std())
    print(f"\n5-Fold CV Accuracy: {cv_mean:.3f} +/- {cv_std:.3f}")
    print(f"Per-fold scores:    {[round(s, 3) for s in cv_scores.tolist()]}")

    # Final fit on all data
    ensemble.fit(X, y)
    y_pred = ensemble.predict(X)
    report = classification_report(y, y_pred, target_names=["Dismissed", "Allowed"])
    print(f"\nTrain-set report:\n{report}")

    joblib.dump(ensemble, _model_path())
    logger.info(f"Model saved -> {_model_path()}")

    meta = {
        "cv_accuracy_mean": round(cv_mean, 4),
        "cv_accuracy_std":  round(cv_std, 4),
        "cv_scores":        [round(s, 4) for s in cv_scores.tolist()],
        "train_samples":    len(X),
        "class_counts":     class_counts,
        "model_type":       "VotingClassifier(CalibratedSVM+LR, isotonic)",
    }
    _meta_path().write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Metadata saved -> {_meta_path()}")

    global _clf, _meta
    _clf  = None
    _meta = None


def predict(text: str) -> tuple[int | None, float | None]:
    """
    Returns (label, calibrated_confidence) or (None, None).

    Uses a calibrated decision threshold to handle class imbalance:
    - Dataset is ~79% Allowed, 21% Dismissed
    - Default 0.5 threshold is biased toward Allowed
    - We use threshold=0.65 for Allowed: only predict Allowed if P(Allowed) >= 0.65
    - This reduces false "Favorable" predictions on ambiguous/disposed cases
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
        proba  = clf.predict_proba(emb_2d)[0]

        # proba[0] = P(Dismissed), proba[1] = P(Allowed)
        p_dismissed = float(proba[0])
        p_allowed   = float(proba[1])

        # Calibrated threshold: require stronger evidence for "Allowed"
        # given the 79:21 class imbalance
        ALLOWED_THRESHOLD = 0.62

        if p_allowed >= ALLOWED_THRESHOLD:
            label = 1
            conf  = p_allowed
        else:
            label = 0
            conf  = p_dismissed

        conf = max(0.50, min(0.99, conf))
        return label, conf
    except Exception as e:
        logger.error(f"predict failed: {e}")
        return None, None

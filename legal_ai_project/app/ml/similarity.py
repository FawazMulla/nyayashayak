"""
Module 7 — Similarity Search (Enhanced)
=========================================
Uses mean-centered cosine similarity on InLegalBERT embeddings.

The core problem with raw cosine similarity on legal text:
  All judgments share vocabulary ("High Court", "appeal", "section") which
  creates a strong shared "legal domain" component in every embedding.
  Raw cosine similarity measures this shared component, not actual case similarity.

Fix — Mean Centering (document centering):
  Subtract the dataset mean embedding from every vector before computing similarity.
  This removes the shared "legal domain" direction, leaving only the
  case-specific variance — facts, sections, parties, legal issue.
  Result: similarity now reflects actual case content, not shared vocabulary.

Score display:
  Centered cosine scores are in [-1, 1]. We map the useful range [0.1, 0.7]
  to [0, 100]% for display. Scores outside this range are filtered out.
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)

# After centering, valid similarity range
_SCORE_MIN = 0.05   # below = unrelated
_SCORE_MAX = 0.75   # above = suspiciously high (near-duplicate)

# ── Singleton cache ───────────────────────────────────────────────────────────
_dataset_embs  = None   # shape (N, 768), mean-centered + L2-normalised
_dataset_texts = None   # list[str] of original input_text strings
_mean_emb      = None   # shape (768,) — dataset mean for centering queries


def _load_once():
    global _dataset_embs, _dataset_texts, _mean_emb
    if _dataset_embs is not None:
        return True

    from .embeddings import load_dataset_embeddings
    embs, texts = load_dataset_embeddings()
    if embs is None or len(embs) == 0:
        logger.warning("Similarity: no dataset embeddings found — run build_ml")
        return False

    embs = embs.astype(np.float32)

    # ── Mean centering ────────────────────────────────────────────────────────
    # Compute dataset mean and subtract — removes shared "legal domain" component
    _mean_emb = embs.mean(axis=0)                    # shape (768,)
    centered  = embs - _mean_emb                     # shape (N, 768)

    # L2-normalise centered vectors
    norms = np.linalg.norm(centered, axis=1, keepdims=True)
    norms = np.where(norms < 1e-9, 1.0, norms)
    _dataset_embs  = (centered / norms).astype(np.float32)
    _dataset_texts = texts

    logger.info(f"Similarity: loaded {len(texts)} mean-centered embeddings")
    return True


def find_similar(text: str, top_k: int = 5) -> list[dict]:
    """
    Find top_k semantically similar cases using mean-centered cosine similarity.

    Returns list of dicts: [{"text": "...", "score": 73.2}, ...]
    score is a percentage in [0, 100] mapped from the valid similarity band.
    Returns [] on failure or if no results pass the threshold.
    """
    if not _load_once():
        return []

    from .embeddings import get_embedding
    emb = get_embedding(text)
    if emb is None:
        return []

    try:
        emb = emb.astype(np.float32)

        # Center the query using the same dataset mean
        centered_q = emb - _mean_emb

        norm = np.linalg.norm(centered_q)
        if norm < 1e-9:
            return []
        q = (centered_q / norm).astype(np.float32)

        # Vectorised cosine similarity on centered vectors
        scores = _dataset_embs @ q   # shape (N,)

        top_idx = np.argsort(scores)[::-1]

        results = []
        for idx in top_idx:
            score = float(scores[idx])

            # Skip near-duplicates (same or nearly same document)
            if score >= 0.999:
                continue

            # Filter to meaningful range
            if score < _SCORE_MIN or score > _SCORE_MAX:
                continue

            # Map [_SCORE_MIN, _SCORE_MAX] → [0, 100] for display
            scaled = (score - _SCORE_MIN) / (_SCORE_MAX - _SCORE_MIN) * 100
            scaled = round(min(max(scaled, 0.0), 100.0), 1)

            snippet = _dataset_texts[idx]
            results.append({
                "text":  snippet[:300] + ("…" if len(snippet) > 300 else ""),
                "score": scaled,
            })

            if len(results) >= top_k:
                break

        return results

    except Exception as e:
        logger.error(f"find_similar failed: {e}")
        return []

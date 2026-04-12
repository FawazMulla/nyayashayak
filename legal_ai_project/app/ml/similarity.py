"""
Module 7 — Similarity Search
==============================
Finds top-K most similar cases from the dataset using cosine similarity
on precomputed InLegalBERT embeddings.

Singleton: dataset embeddings loaded once into memory.
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)

# ── Singleton cache ───────────────────────────────────────────────────────────
_dataset_embs  = None   # shape (N, 768), float32, L2-normalised
_dataset_texts = None   # list[str] of input_text strings


def _load_once():
    global _dataset_embs, _dataset_texts
    if _dataset_embs is not None:
        return True
    from .embeddings import load_dataset_embeddings
    embs, texts = load_dataset_embeddings()
    if embs is None or len(embs) == 0:
        logger.warning("Similarity: no dataset embeddings found")
        return False
    # L2-normalise once so dot product == cosine similarity
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    _dataset_embs  = (embs / norms).astype(np.float32)
    _dataset_texts = texts
    logger.info(f"Similarity: loaded {len(texts)} dataset embeddings")
    return True


def find_similar(text: str, top_k: int = 5) -> list[dict]:
    """
    Find top_k most similar cases to `text`.

    Returns list of dicts:
        [{"text": "...", "score": 0.87}, ...]
    Returns [] on any failure.
    """
    if not _load_once():
        return []

    from .embeddings import get_embedding
    emb = get_embedding(text)
    if emb is None:
        return []

    try:
        # Normalise query
        norm = np.linalg.norm(emb)
        if norm == 0:
            return []
        q = (emb / norm).astype(np.float32)

        # Vectorised cosine similarity (dot product on normalised vectors)
        scores = _dataset_embs @ q          # shape (N,)

        # Top-K indices (excluding perfect 1.0 match = same document)
        top_idx = np.argsort(scores)[::-1]
        results = []
        for idx in top_idx:
            score = float(scores[idx])
            if score >= 0.9999:             # skip exact self-match
                continue
            snippet = _dataset_texts[idx]
            results.append({
                "text":    snippet[:300] + ("…" if len(snippet) > 300 else ""),
                "score":   round(score * 100, 1),   # as percentage
            })
            if len(results) >= top_k:
                break
        return results

    except Exception as e:
        logger.error(f"find_similar failed: {e}")
        return []

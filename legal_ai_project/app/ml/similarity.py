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
import json
import numpy as np

logger = logging.getLogger(__name__)

_SCORE_MIN = 0.05
_SCORE_MAX = 0.75

_dataset_embs  = None
_dataset_texts = None
_mean_emb      = None
_sim_meta      = None   # list[dict] with case_id, outcome, category, sections


def _load_once():
    global _dataset_embs, _dataset_texts, _mean_emb, _sim_meta
    if _dataset_embs is not None:
        return True

    from .embeddings import load_dataset_embeddings, _data_dir
    embs, texts = load_dataset_embeddings()
    if embs is None or len(embs) == 0:
        logger.warning("Similarity: no dataset embeddings found — run build_ml")
        return False

    embs = embs.astype(np.float32)
    _mean_emb = embs.mean(axis=0)
    centered  = embs - _mean_emb
    norms = np.linalg.norm(centered, axis=1, keepdims=True)
    norms = np.where(norms < 1e-9, 1.0, norms)
    _dataset_embs  = (centered / norms).astype(np.float32)
    _dataset_texts = texts

    # Load rich metadata if available
    sim_meta_path = _data_dir() / "similarity_meta.json"
    if sim_meta_path.exists():
        try:
            _sim_meta = json.loads(sim_meta_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Could not load similarity_meta.json: {e}")
            _sim_meta = None
    else:
        _sim_meta = None

    logger.info(f"Similarity: loaded {len(texts)} mean-centered embeddings")
    return True


def find_similar(text: str, top_k: int = 5) -> list[dict]:
    """
    Find top_k semantically similar cases using mean-centered cosine similarity.

    Returns list of dicts:
      {
        "text": "...",          # input_text snippet (300 chars)
        "score": 73.2,          # similarity % [0-100]
        "case_id": "2025 INSC 35",
        "outcome": "Allowed",
        "category": "Criminal",
        "sections": "302 IPC, 34 IPC",
      }
    Falls back to text-only if similarity_meta.json not available.
    """
    if not _load_once():
        return []

    from .embeddings import get_embedding
    emb = get_embedding(text)
    if emb is None:
        return []

    try:
        emb = emb.astype(np.float32)
        centered_q = emb - _mean_emb
        norm = np.linalg.norm(centered_q)
        if norm < 1e-9:
            return []
        q = (centered_q / norm).astype(np.float32)

        scores  = _dataset_embs @ q
        top_idx = np.argsort(scores)[::-1]

        results = []
        for idx in top_idx:
            score = float(scores[idx])
            if score >= 0.999:
                continue
            if score < _SCORE_MIN or score > _SCORE_MAX:
                continue

            scaled = (score - _SCORE_MIN) / (_SCORE_MAX - _SCORE_MIN) * 100
            scaled = round(min(max(scaled, 0.0), 100.0), 1)

            snippet = _dataset_texts[idx]
            entry = {
                "text":  snippet[:300] + ("..." if len(snippet) > 300 else ""),
                "score": scaled,
                "case_id":  "",
                "outcome":  "",
                "category": "",
                "sections": "",
            }

            # Enrich with metadata if available
            if _sim_meta and idx < len(_sim_meta):
                m = _sim_meta[idx]
                entry["case_id"]  = m.get("case_id", "")
                entry["outcome"]  = m.get("outcome", "")
                entry["category"] = m.get("category", "")
                entry["sections"] = m.get("sections", "")

            results.append(entry)
            if len(results) >= top_k:
                break

        return results

    except Exception as e:
        logger.error(f"find_similar failed: {e}")
        return []

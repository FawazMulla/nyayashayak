"""
Module 5 — Feature Engineering (Embeddings)
============================================
Converts legal input_text → 768-dim vector using InLegalBERT.
Singleton pattern: model loads once, reused across all requests.
"""

import logging
import numpy as np
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)

# Local model path inside the repo — download files from:
# https://huggingface.co/law-ai/InLegalBERT/tree/main
# and place them in legal_ai_project/models/InLegalBERT/
_LOCAL_MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "InLegalBERT"

def _model_source() -> str:
    """
    Use local repo path if all required model files exist.
    Raises RuntimeError if local files are missing — we do NOT auto-download
    from HuggingFace in production. Run build_ml after placing model files.
    """
    required = ["config.json", "tokenizer_config.json", "vocab.txt", "pytorch_model.bin"]
    if all((_LOCAL_MODEL_DIR / f).exists() for f in required):
        return str(_LOCAL_MODEL_DIR)
    # Check for safetensors variant too
    required_safe = ["config.json", "tokenizer_config.json", "vocab.txt", "model.safetensors"]
    if all((_LOCAL_MODEL_DIR / f).exists() for f in required_safe):
        return str(_LOCAL_MODEL_DIR)
    missing = [f for f in required if not (_LOCAL_MODEL_DIR / f).exists()]
    logger.error(
        f"InLegalBERT model files missing from {_LOCAL_MODEL_DIR}: {missing}. "
        "Place model files there or run: git lfs pull"
    )
    return str(_LOCAL_MODEL_DIR)  # return path anyway, transformers will give a clear error
MAX_TOKENS   = 512
EMBED_FILE   = "embeddings.npy"
META_FILE    = "embeddings_meta.npy"   # stores input_text strings for similarity

# ── Singletons ────────────────────────────────────────────────────────────────
_tokenizer = None
_model     = None


def load_model():
    """Load InLegalBERT once and cache globally. Returns (tokenizer, model)."""
    global _tokenizer, _model
    if _tokenizer is not None:
        return _tokenizer, _model
    try:
        from transformers import AutoTokenizer, AutoModel
        import torch  # noqa — confirm available
        source = _model_source()
        logger.info(f"Loading InLegalBERT from: {source}")
        _tokenizer = AutoTokenizer.from_pretrained(source)
        _model     = AutoModel.from_pretrained(source)
        _model.eval()
        logger.info("InLegalBERT loaded OK")
    except Exception as e:
        logger.error(f"Failed to load InLegalBERT: {e}")
        _tokenizer = None
        _model     = None
    return _tokenizer, _model


def get_embedding(text: str) -> np.ndarray | None:
    """
    Embed a single text string → numpy array shape (768,).
    Returns None on any failure.
    """
    tokenizer, model = load_model()
    if tokenizer is None:
        return None
    try:
        import torch
        enc = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=MAX_TOKENS,
            padding=True,
        )
        with torch.no_grad():
            out = model(**enc)
        # Mean pooling over token dimension
        mask = enc["attention_mask"].unsqueeze(-1).float()
        emb  = (out.last_hidden_state * mask).sum(1) / mask.sum(1)
        return emb.squeeze(0).numpy()
    except Exception as e:
        logger.error(f"get_embedding failed: {e}")
        return None


def get_embeddings_batch(texts: list[str], batch_size: int = 16) -> np.ndarray | None:
    """
    Embed a list of texts in batches → numpy array shape (N, 768).
    Returns None on failure.
    """
    tokenizer, model = load_model()
    if tokenizer is None:
        return None
    try:
        import torch
        all_embs = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i: i + batch_size]
            enc   = tokenizer(
                batch,
                return_tensors="pt",
                truncation=True,
                max_length=MAX_TOKENS,
                padding=True,
            )
            with torch.no_grad():
                out = model(**enc)
            mask = enc["attention_mask"].unsqueeze(-1).float()
            emb  = (out.last_hidden_state * mask).sum(1) / mask.sum(1)
            all_embs.append(emb.numpy())
        return np.vstack(all_embs)
    except Exception as e:
        logger.error(f"get_embeddings_batch failed: {e}")
        return None


def _data_dir() -> Path:
    return Path(settings.DATA_DIR)


def save_dataset_embeddings(texts: list[str], meta_records: list[dict] | None = None):
    """
    Compute and save embeddings for the full dataset.
    Run once via management command or train script.
    Saves: data/embeddings.npy  (float32, shape N x 768)
           data/embeddings_meta.npy  (object array of input_text strings)
           data/similarity_meta.json (rich metadata per entry: case_id, outcome, category, sections)
    """
    embs = get_embeddings_batch(texts)
    if embs is None:
        logger.error("save_dataset_embeddings: embedding failed, nothing saved")
        return
    d = _data_dir()
    d.mkdir(parents=True, exist_ok=True)
    np.save(d / EMBED_FILE, embs.astype(np.float32))
    np.save(d / META_FILE,  np.array(texts, dtype=object))

    # Save rich metadata if provided
    if meta_records:
        import json
        sim_meta_path = d / "similarity_meta.json"
        sim_meta_path.write_text(
            json.dumps(meta_records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"Saved similarity metadata -> {sim_meta_path}")

    logger.info(f"Saved {len(texts)} embeddings -> {d / EMBED_FILE}")


def load_dataset_embeddings() -> tuple[np.ndarray | None, list[str] | None]:
    """
    Load precomputed dataset embeddings from disk.
    Returns (embeddings_array, texts_list) or (None, None) if not found.
    """
    d = _data_dir()
    ep = d / EMBED_FILE
    mp = d / META_FILE
    if not ep.exists() or not mp.exists():
        return None, None
    try:
        embs  = np.load(ep)
        texts = np.load(mp, allow_pickle=True).tolist()
        return embs, texts
    except Exception as e:
        logger.error(f"load_dataset_embeddings failed: {e}")
        return None, None

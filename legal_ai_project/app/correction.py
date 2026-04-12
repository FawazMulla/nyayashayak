"""
Hybrid Correction Pipeline — NUC Legal AI
==========================================
Pipeline: Extractor → Sanity Check → (if needed) Single Cohere call → Final Output

Single API call does BOTH:
  - Field correction (sections, category, appellant)
  - AI summary (replaces rule-based input_text when AI is on)

Toggle AI on/off via .env:  AI_CORRECTION_ENABLED=true|false
"""

import json
import re
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


# ── Legal document validator ──────────────────────────────────────────────────
# These are COURT-SPECIFIC terms — unlikely in random docs with "section 3.1"
_STRONG_SIGNALS = [
    r"\bappellant\b",
    r"\brespondent\b",
    r"\bpetitioner\b",
    r"\bhon['']?ble\b",
    r"\bjustice\b",
    r"\bsupreme\s+court\b",
    r"\bhigh\s+court\b",
    r"\bconviction\b",
    r"\bacquitted?\b",
    r"\binsc\b",
    r"\bslp\b",
    r"\bcriminal\s+appeal\b",
    r"\bcivil\s+appeal\b",
    r"\bwrit\s+petition\b",
    r"\bjudgment\b",
    r"\bhereby\s+(?:allowed|dismissed|quashed|disposed)\b",
    r"\bappeal\s+(?:is|are|stands?)\s+(?:allowed|dismissed)\b",
    r"\bstand[s]?\s+disposed\b",
    r"\bimpugned\s+(?:order|judgment)\b",
    r"\b(?:ipc|crpc|bnss?|cpc)\b",
]
_MIN_STRONG_HITS = 4   # needs 4 court-specific hits — random docs won't pass
_MIN_WORD_COUNT  = 100


def is_legal_document(text: str) -> tuple[bool, str]:
    """
    Strict check — only passes genuine court judgments.
    Returns (True, "") or (False, user-facing reason).
    """
    words = len(text.split())
    if words < _MIN_WORD_COUNT:
        return False, (
            f"Document too short ({words} words). "
            "Please provide a complete judgment text."
        )

    tl = text.lower()
    hits = sum(1 for pat in _STRONG_SIGNALS if re.search(pat, tl))

    if hits < _MIN_STRONG_HITS:
        return False, (
            "This does not appear to be a court judgment. "
            "Please upload a Supreme Court or High Court judgment PDF, "
            "or paste the full judgment text."
        )

    return True, ""


# ── Lazy Cohere client ────────────────────────────────────────────────────────
_co = None

def _get_client():
    global _co
    if _co is None:
        try:
            import cohere
            api_key = getattr(settings, "COHERE_API_KEY", "") or ""
            if not api_key:
                return None
            _co = cohere.ClientV2(api_key=api_key)
        except Exception as e:
            logger.warning(f"Cohere client init failed: {e}")
            return None
    return _co


def _ai_enabled() -> bool:
    return getattr(settings, "AI_CORRECTION_ENABLED", True)


# ── Rule-based sanity check ───────────────────────────────────────────────────

def detect_issues(data: dict, text: str) -> list[str]:
    issues   = []
    sections  = data.get("sections", "") or ""
    appellant = data.get("appellant", "") or ""
    category  = data.get("category", "") or ""

    if "509 IT Act" in sections:           issues.append("sections")
    if "509 TN" in sections:               issues.append("sections")
    if sections.count("509") > 1:          issues.append("sections")
    if re.search(r"\b(302|376|420|498)\s+(?!IPC|BNS)", sections):
        issues.append("sections")

    tokens = appellant.split()
    if tokens and len(tokens[0]) > 20:     issues.append("appellant")

    tl = text.lower()
    if ("criminal" in tl and "writ" in tl
            and category.lower() == "constitutional / writ"):
        issues.append("category")

    return list(set(issues))


# ── Single combined Cohere call ───────────────────────────────────────────────

def _build_combined_prompt(issues: list[str], data: dict, context: str) -> str:
    """
    One prompt that asks Cohere to return BOTH a summary AND field corrections.
    Minimises API calls to exactly one.
    """
    doc_name = data.get("filename", "document") or "document"
    relevant = {k: data.get(k, "") for k in issues} if issues else {}

    correction_block = ""
    if issues:
        correction_block = f"""
Also fix ONLY these extracted fields (they have errors): {issues}
Current wrong values: {json.dumps(relevant)}

Field correction rules:
- sections format: "302 IPC, 376 IPC, 4 TN Harassment of Women Act"
- category choices: Criminal, Criminal - Writ, Civil, Constitutional / Writ, SLP, Tax, Service Law, Family Law, Labour / Industrial, Electoral, Environmental, Corporate / Securities, Other
- appellant: clean name from text header, no hash/UUID prefixes
- Do NOT hallucinate values not present in the text
"""

    return f"""You are a legal AI assistant for Indian Supreme Court judgments.

Document: {doc_name}
Legal text (first 2000 chars):
{context}
{correction_block}
Respond with valid JSON only (no markdown, no explanation):
{{
  "summary": "4-6 sentence plain-text summary: document type, parties, main legal issue, outcome",
  "corrections": {json.dumps({k: "..." for k in issues}) if issues else "{}"}
}}"""


def run_ai_pipeline(data: dict, raw_text: str) -> tuple[str, dict]:
    """
    Single Cohere call that returns (summary_text, corrections_dict).
    corrections_dict is empty if no issues or AI unavailable.
    Falls back gracefully on any error.
    """
    if not _ai_enabled():
        return "", {}

    co = _get_client()
    if co is None:
        return "", {}

    issues  = detect_issues(data, raw_text)
    context = raw_text[:2000].strip()
    prompt  = _build_combined_prompt(issues, data, context)

    try:
        response     = co.chat(
            model="command-r",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        raw_resp = response.message.content[0].text.strip()
        raw_resp = re.sub(r"^```(?:json)?\s*", "", raw_resp)
        raw_resp = re.sub(r"\s*```$",           "", raw_resp)
        parsed   = json.loads(raw_resp)

        summary     = parsed.get("summary", "") or ""
        corrections = parsed.get("corrections", {}) or {}
        return summary, corrections

    except Exception as e:
        logger.warning(f"run_ai_pipeline failed: {e}")
        return "", {}


# ── Public entry points ───────────────────────────────────────────────────────

def hybrid_correction(data: dict, raw_text: str) -> dict:
    """
    Runs the full AI pipeline (one call) or falls back to rule-based.
    Sets:
      data["ai_summary"]           — AI summary string (empty if AI off/failed)
      data["ai_corrected"]         — bool
      data["ai_corrected_fields"]  — list of field names fixed
      data["ai_skip_reason"]       — reason string when AI was skipped
    """
    summary, corrections = run_ai_pipeline(data, raw_text)

    # Store summary — used in result.html instead of rule-based input_text
    data["ai_summary"] = summary

    if not corrections:
        issues = detect_issues(data, raw_text)
        reason = "AI disabled" if not _ai_enabled() else (
                 "no API key"  if _get_client() is None else
                 "no issues detected" if not issues else
                 "AI call failed")
        data["ai_corrected"]        = False
        data["ai_corrected_fields"] = []
        data["ai_skip_reason"]      = reason
        return data

    # Merge corrections for flagged fields only
    issues  = detect_issues(data, raw_text)
    applied = []
    for key in issues:
        val = corrections.get(key, "")
        if val and val != "...":
            data[key] = val
            applied.append(key)

    data["ai_corrected"]        = bool(applied)
    data["ai_corrected_fields"] = applied
    data["ai_skip_reason"]      = ""
    logger.info(f"hybrid_correction: applied={applied}, summary={'yes' if summary else 'no'}")
    return data

"""
NUC Legal AI — Chatbot Core
============================
Uses CHATBOT_API_KEY (Oracle Cloud Cohere) — completely separate from the
extractor pipeline which uses COHERE_API_KEY.

Toggle via .env:
  CHATBOT_ENABLED=true|false
  CHATBOT_API_KEY=your_oracle_cohere_key
"""

import logging
from django.conf import settings
from . import prompts

logger = logging.getLogger(__name__)

_CHATBOT_MODEL = "command-a-03-2025"

# ── Isolated Cohere client — CHATBOT_API_KEY only ─────────────────────────────
_co = None

def _get_client():
    """Uses CHATBOT_API_KEY — chatbot only, never touches extractor pipeline."""
    global _co
    if _co is None:
        try:
            import cohere
            api_key = getattr(settings, "CHATBOT_API_KEY", "") or ""
            if not api_key:
                return None
            _co = cohere.ClientV2(api_key=api_key)
        except Exception as e:
            logger.warning(f"Chatbot Cohere client init failed: {e}")
            return None
    return _co


def _chatbot_enabled() -> bool:
    return getattr(settings, "CHATBOT_ENABLED", True)


def _call(prompt: str) -> str:
    """Single Cohere chat call via chatbot client. Never raises."""
    if not _chatbot_enabled():
        return "⚠️ Chatbot is currently disabled (CHATBOT_ENABLED=false)."

    co = _get_client()
    if co is None:
        return "⚠️ Chatbot unavailable — CHATBOT_API_KEY not configured."

    try:
        resp = co.chat(
            model=_CHATBOT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return resp.message.content[0].text.strip()
    except Exception as e:
        logger.error(f"Chatbot API call failed: {e}")
        return f"⚠️ AI response failed: {e}"


# ── Quick-action dispatch ─────────────────────────────────────────────────────
QUICK_ACTIONS = {
    "explain":   lambda ctx: _call(prompts.explain_case(ctx)),
    "nextsteps": lambda ctx: _call(prompts.next_steps(ctx)),
    "risk":      lambda ctx: _call(prompts.risk_analysis(ctx)),
    "arguments": lambda ctx: _call(prompts.generate_arguments(ctx)),
    "compare":   lambda ctx: _call(prompts.compare_cases(ctx)),
    "eli5":      lambda ctx: _call(prompts.eli5(ctx)),
}


def generate_chat_response(user_query: str, context: dict, action: str = "") -> str:
    """
    Main entry point called from views.chatbot_api.

    Args:
        user_query: Free-text question (empty for quick actions)
        context:    Case context dict from request.session
        action:     Quick-action key: explain/nextsteps/risk/arguments/compare/eli5

    Returns:
        Response string — always, never raises.
    """
    if not context:
        return "⚠️ No case context found. Please analyze a case first."

    if action and action in QUICK_ACTIONS:
        return QUICK_ACTIONS[action](context)

    if not user_query or not user_query.strip():
        return "Please type a question or click one of the quick-action buttons."

    return _call(prompts.general_query(context, user_query.strip()))

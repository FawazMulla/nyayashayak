"""
NUC Legal AI — Chatbot Core
============================
Uses OCI Generative AI (Oracle Cloud) — completely separate from the
extractor pipeline which uses COHERE_API_KEY via Cohere SDK.

Config via .env:
  CHATBOT_ENABLED=true|false
  OCI_USER_OCID, OCI_TENANCY_OCID, OCI_FINGERPRINT,
  OCI_PRIVATE_KEY_PATH, OCI_REGION, OCI_COMPARTMENT_ID,
  OCI_CHAT_MODEL_ID
"""

import logging
from django.conf import settings
from . import prompts
from .prompt_config import CASE_SYSTEM, LINCOLN_SYSTEM

logger = logging.getLogger(__name__)

# ── OCI client singleton ──────────────────────────────────────────────────────
_oci_client = None
_init_attempted = False


def _get_client():
    """Build OCI GenerativeAiInferenceClient once using key-based auth."""
    global _oci_client, _init_attempted
    if _init_attempted:
        return _oci_client
    _init_attempted = True
    try:
        import oci
        cfg = {
            "user":        getattr(settings, "OCI_USER_OCID", ""),
            "tenancy":     getattr(settings, "OCI_TENANCY_OCID", ""),
            "fingerprint": getattr(settings, "OCI_FINGERPRINT", ""),
            "key_file":    getattr(settings, "OCI_PRIVATE_KEY_PATH", ""),
            "region":      getattr(settings, "OCI_REGION", ""),
        }
        missing = [k for k, v in cfg.items() if not v]
        if missing:
            logger.error(f"OCI config missing fields: {missing}")
            return None

        _oci_client = oci.generative_ai_inference.GenerativeAiInferenceClient(
            config=cfg,
            service_endpoint=f"https://inference.generativeai.{cfg['region']}.oci.oraclecloud.com",
        )
        logger.info("OCI GenerativeAI client initialised successfully")
    except Exception as e:
        logger.error(f"OCI client init failed: {e}")
        return None
    return _oci_client


def _chatbot_enabled() -> bool:
    try:
        from app.models import AISettings
        return AISettings.get().oci_enabled
    except Exception:
        return getattr(settings, "CHATBOT_ENABLED", True)


# ── OCI chat call ─────────────────────────────────────────────────────────────

def _call(user_prompt: str, system_prompt: str = "", history: list | None = None) -> str:
    """Make a single OCI Generative AI chat call with optional conversation history."""
    if not _chatbot_enabled():
        return "Chatbot is currently disabled."

    client = _get_client()
    if client is None:
        return "Chatbot unavailable — OCI credentials not configured."

    try:
        import oci
        model_id    = getattr(settings, "OCI_CHAT_MODEL_ID", "cohere.command-a-03-2025")
        compartment = settings.OCI_COMPARTMENT_ID

        # Build chat history for multi-turn memory
        chat_history = []
        if history:
            for turn in history[-6:]:   # last 3 exchanges (6 messages)
                role = turn.get("role", "user").upper()
                msg  = turn.get("content", "")
                if role == "USER":
                    chat_history.append(
                        oci.generative_ai_inference.models.CohereUserMessage(
                            role="USER", message=msg
                        )
                    )
                else:
                    chat_history.append(
                        oci.generative_ai_inference.models.CohereChatBotMessage(
                            role="CHATBOT", message=msg
                        )
                    )

        details = oci.generative_ai_inference.models.CohereChatRequest(
            message=user_prompt,
            chat_history=chat_history,
            preamble_override=system_prompt or None,
            max_tokens=500,       # increased from 300 — avoids cut-off responses
            temperature=0.3,      # slightly higher — less robotic
            is_stream=False,
        )

        response = client.chat(
            oci.generative_ai_inference.models.ChatDetails(
                compartment_id=compartment,
                serving_mode=oci.generative_ai_inference.models.OnDemandServingMode(
                    model_id=model_id
                ),
                chat_request=details,
            )
        )
        return response.data.chat_response.text.strip()

    except Exception as e:
        logger.error(f"OCI chat call failed: {e}")
        return f"AI response failed: {e}"


# ── Quick-action dispatch ─────────────────────────────────────────────────────
_CASE_SYSTEM = CASE_SYSTEM
_LINCOLN_SYSTEM = LINCOLN_SYSTEM

QUICK_ACTIONS = {
    "explain":   lambda ctx, h: _call(prompts.explain_case(ctx),        _CASE_SYSTEM, h),
    "nextsteps": lambda ctx, h: _call(prompts.next_steps(ctx),          _CASE_SYSTEM, h),
    "risk":      lambda ctx, h: _call(prompts.risk_analysis(ctx),       _CASE_SYSTEM, h),
    "arguments": lambda ctx, h: _call(prompts.generate_arguments(ctx),  _CASE_SYSTEM, h),
    "compare":   lambda ctx, h: _call(prompts.compare_cases(ctx),       _CASE_SYSTEM, h),
    "eli5":      lambda ctx, h: _call(prompts.eli5(ctx),                _CASE_SYSTEM, h),
}

LINCOLN_ACTIONS = {
    "general": lambda h: _call(prompts.lincoln_procedures(),     _LINCOLN_SYSTEM, h),
    "rights":  lambda h: _call(prompts.lincoln_rights(),         _LINCOLN_SYSTEM, h),
    "bail":    lambda h: _call(prompts.lincoln_bail(),           _LINCOLN_SYSTEM, h),
    "appeal":  lambda h: _call(prompts.lincoln_appeal(),         _LINCOLN_SYSTEM, h),
    "explain": lambda h: _call(prompts.lincoln_explain_prompt(), _LINCOLN_SYSTEM, h),
    "eli5":    lambda h: _call(prompts.lincoln_eli5_prompt(),    _LINCOLN_SYSTEM, h),
}


def generate_chat_response(
    user_query: str,
    context: dict,
    action: str = "",
    mode: str = "case",
    history: list | None = None,
) -> str:
    """
    Main entry point.
    history: list of {"role": "user"|"assistant", "content": "..."} dicts
             for multi-turn conversation memory (last 3 exchanges used).
    """
    query   = (user_query or "").strip()
    history = history or []

    if mode == "lincoln":
        if action and action in LINCOLN_ACTIONS:
            return LINCOLN_ACTIONS[action](history)
        if not query:
            return "Please type a legal question."
        return _call(prompts.lincoln_query(query), _LINCOLN_SYSTEM, history)

    if not context:
        return "No case context found. Please analyze a case first."

    if action and action in QUICK_ACTIONS:
        return QUICK_ACTIONS[action](context, history)

    if not query:
        return "Please type a question or click one of the quick-action buttons."

    return _call(prompts.general_query(context, query), _CASE_SYSTEM, history)

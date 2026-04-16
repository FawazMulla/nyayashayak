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

def _call(user_prompt: str, system_prompt: str = "") -> str:
    """Make a single OCI Generative AI chat call. Never raises."""
    if not _chatbot_enabled():
        return "⚠️ Chatbot is currently disabled (CHATBOT_ENABLED=false)."

    client = _get_client()
    if client is None:
        return "⚠️ Chatbot unavailable — OCI credentials not configured correctly."

    try:
        import oci
        model_id      = getattr(settings, "OCI_CHAT_MODEL_ID", "cohere.command-a-03-2025")
        compartment   = settings.OCI_COMPARTMENT_ID

        messages = []
        if system_prompt:
            messages.append(
                oci.generative_ai_inference.models.CohereSystemMessage(
                    role="SYSTEM", message=system_prompt
                )
            )
        messages.append(
            oci.generative_ai_inference.models.CohereUserMessage(
                role="USER", message=user_prompt
            )
        )

        details = oci.generative_ai_inference.models.CohereChatRequest(
            message=user_prompt,
            chat_history=messages[:-1] if len(messages) > 1 else [],
            preamble_override=system_prompt or None,
            max_tokens=300,
            temperature=0.2,
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
        return f"⚠️ AI response failed: {e}"


# ── Quick-action dispatch ─────────────────────────────────────────────────────
_CASE_SYSTEM = CASE_SYSTEM
_LINCOLN_SYSTEM = LINCOLN_SYSTEM

QUICK_ACTIONS = {
    "explain":   lambda ctx: _call(prompts.explain_case(ctx),   _CASE_SYSTEM),
    "nextsteps": lambda ctx: _call(prompts.next_steps(ctx),     _CASE_SYSTEM),
    "risk":      lambda ctx: _call(prompts.risk_analysis(ctx),  _CASE_SYSTEM),
    "arguments": lambda ctx: _call(prompts.generate_arguments(ctx), _CASE_SYSTEM),
    "compare":   lambda ctx: _call(prompts.compare_cases(ctx),  _CASE_SYSTEM),
    "eli5":      lambda ctx: _call(prompts.eli5(ctx),           _CASE_SYSTEM),
}

LINCOLN_ACTIONS = {
    "general":  lambda: _call(prompts.lincoln_procedures(),    _LINCOLN_SYSTEM),
    "rights":   lambda: _call(prompts.lincoln_rights(),        _LINCOLN_SYSTEM),
    "bail":     lambda: _call(prompts.lincoln_bail(),          _LINCOLN_SYSTEM),
    "appeal":   lambda: _call(prompts.lincoln_appeal(),        _LINCOLN_SYSTEM),
    "explain":  lambda: _call(prompts.lincoln_explain_prompt(), _LINCOLN_SYSTEM),
    "eli5":     lambda: _call(prompts.lincoln_eli5_prompt(),   _LINCOLN_SYSTEM),
}


def generate_chat_response(user_query: str, context: dict, action: str = "", mode: str = "case") -> str:
    """
    Main entry point.
    mode="lincoln" → general legal assistant, no case restriction
    mode="case"    → strict case-only assistant
    """
    query = (user_query or "").strip()

    # ── Lincoln Lawyer — general legal Q&A ───────────────────────────────────
    if mode == "lincoln":
        if action and action in LINCOLN_ACTIONS:
            return LINCOLN_ACTIONS[action]()
        if not query:
            return "Please type a legal question."
        return _call(prompts.lincoln_query(query), _LINCOLN_SYSTEM)

    # ── Case mode — strict case-only ──────────────────────────────────────────
    if not context:
        return "⚠️ No case context found. Please analyze a case first."

    if action and action in QUICK_ACTIONS:
        return QUICK_ACTIONS[action](context)

    if not query:
        return "Please type a question or click one of the quick-action buttons."

    return _call(prompts.general_query(context, query), _CASE_SYSTEM)

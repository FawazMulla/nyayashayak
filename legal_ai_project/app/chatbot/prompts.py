"""
Prompt builder — reads all strings from prompt_config.py.
Do NOT edit prompts here. Edit prompt_config.py instead.
"""
from . import prompt_config as cfg


def _case_block(ctx: dict) -> str:
    """Build a rich case context block for injection into prompts."""
    sim = ctx.get("similar_cases", [])[:3]
    sim_text = ""
    if sim:
        parts = []
        for c in sim:
            outcome_tag = f"[{c.get('outcome', '')}]" if c.get("outcome") else ""
            cat_tag     = f"({c.get('category', '')})" if c.get("category") else ""
            parts.append(f"[{c['score']}% match] {outcome_tag}{cat_tag} {c['text'][:100]}...")
        sim_text = "\nSimilar Precedents:\n" + "\n".join(parts)

    label_map = {1: "Favorable (Allowed)", 0: "Unfavorable (Dismissed)"}
    pred = label_map.get(ctx.get("prediction"), "Undetermined")
    conf = ctx.get("confidence", "N/A")
    if isinstance(conf, float):
        conf = f"{round(conf * 100, 1)}%"

    # Prefer AI summary over rule-based input_text
    summary = ctx.get("summary") or ctx.get("input_text", "N/A")

    return (
        f"Case Summary: {summary}\n"
        f"Appellant: {ctx.get('appellant', 'N/A')} | Category: {ctx.get('category', 'N/A')}\n"
        f"Outcome: {ctx.get('outcome', 'N/A')} | Sections: {ctx.get('sections', 'N/A')}\n"
        f"ML Prediction: {pred} (Confidence: {conf})"
        f"{sim_text}"
    )


# ── Case mode actions ─────────────────────────────────────────────────────────

def general_query(ctx: dict, user_query: str) -> str:
    return cfg.CASE_QUERY.format(case=_case_block(ctx), question=user_query)

def explain_case(ctx: dict) -> str:
    return cfg.CASE_EXPLAIN.format(case=_case_block(ctx))

def next_steps(ctx: dict) -> str:
    return cfg.CASE_NEXT_STEPS.format(case=_case_block(ctx))

def risk_analysis(ctx: dict) -> str:
    return cfg.CASE_RISK.format(case=_case_block(ctx))

def generate_arguments(ctx: dict) -> str:
    return cfg.CASE_ARGUMENTS.format(case=_case_block(ctx))

def compare_cases(ctx: dict) -> str:
    sim = ctx.get("similar_cases", [])[:3]
    if not sim:
        return "No similar cases found in the dataset to compare."
    sim_block = "\n".join(
        f"Case {i+1} [{c['score']}% match]: {c['text'][:150]}"
        for i, c in enumerate(sim)
    )
    return cfg.CASE_COMPARE.format(case=_case_block(ctx), similar=sim_block)

def eli5(ctx: dict) -> str:
    return cfg.CASE_ELI5.format(case=_case_block(ctx))


# ── Lincoln mode actions ──────────────────────────────────────────────────────

def lincoln_query(user_query: str) -> str:
    return cfg.LINCOLN_QUERY.format(question=user_query)

def lincoln_procedures() -> str:
    return cfg.LINCOLN_PROCEDURES

def lincoln_rights() -> str:
    return cfg.LINCOLN_RIGHTS

def lincoln_bail() -> str:
    return cfg.LINCOLN_BAIL

def lincoln_appeal() -> str:
    return cfg.LINCOLN_APPEAL

def lincoln_explain_prompt() -> str:
    return cfg.LINCOLN_EXPLAIN

def lincoln_eli5_prompt() -> str:
    return cfg.LINCOLN_ELI5

"""
Prompt templates for NUC Legal AI Chatbot.
Each function returns a fully-formed prompt string for Cohere.
"""

DISCLAIMER = (
    "\n\n---\n⚠️ *This is an AI-generated response for informational purposes only "
    "and does not constitute legal advice. Consult a qualified lawyer for legal guidance.*"
)


def _case_block(ctx: dict) -> str:
    """Build the shared case context block injected into every prompt."""
    sim = ctx.get("similar_cases", [])[:3]
    sim_text = ""
    if sim:
        sim_text = "\nSimilar Past Cases:\n" + "\n".join(
            f"  - [{c['score']}% match] {c['text'][:120]}…" for c in sim
        )

    label_map = {1: "Favorable (Allowed)", 0: "Unfavorable (Dismissed)"}
    pred = label_map.get(ctx.get("prediction"), "Undetermined")
    conf = ctx.get("confidence", "N/A")
    if isinstance(conf, float):
        conf = f"{round(conf * 100, 1)}%"

    return f"""=== CASE CONTEXT ===
Summary: {ctx.get('summary') or ctx.get('input_text', 'N/A')}
Appellant: {ctx.get('appellant', 'N/A')}
Category: {ctx.get('category', 'N/A')}
Outcome: {ctx.get('outcome', 'N/A')}
Legal Sections: {ctx.get('sections', 'N/A')}
ML Prediction: {pred} (Confidence: {conf}){sim_text}
===================="""


def general_query(ctx: dict, user_query: str) -> str:
    return f"""You are NUC Legal AI, an intelligent legal assistant specializing in Indian Supreme Court judgments.

{_case_block(ctx)}

User Question: {user_query}

Instructions:
- Answer clearly and concisely based on the case context above
- Use simple language unless the user asks for technical detail
- Structure your response with short paragraphs
- Reference specific sections or facts from the case when relevant
- Do NOT fabricate case details not present in the context{DISCLAIMER}"""


def explain_case(ctx: dict) -> str:
    return f"""You are NUC Legal AI, an intelligent legal assistant.

{_case_block(ctx)}

Task: Explain this legal case in simple, clear language that a non-lawyer can understand.

Cover:
1. What the case is about (parties and dispute)
2. The key legal issue
3. What sections of law were involved
4. The court's decision and why
5. What this means practically

Keep it concise — 5 to 8 sentences.{DISCLAIMER}"""


def next_steps(ctx: dict) -> str:
    label = ctx.get("prediction")
    outcome = ctx.get("outcome", "")
    return f"""You are NUC Legal AI, an intelligent legal assistant.

{_case_block(ctx)}

Task: Based on the ML prediction ({label}) and outcome ({outcome}), suggest practical next steps for the appellant/petitioner.

Cover:
1. Immediate actions to take
2. Legal remedies available (appeal, review petition, etc.)
3. Key deadlines or limitations to be aware of
4. Documents or evidence that would strengthen the position

Be practical and specific to Indian legal procedure.{DISCLAIMER}"""


def risk_analysis(ctx: dict) -> str:
    return f"""You are NUC Legal AI, an intelligent legal assistant.

{_case_block(ctx)}

Task: Perform a legal risk analysis for this case.

Analyze:
1. Strength of the legal position (based on sections cited and outcome)
2. Key risks and weaknesses
3. Factors that worked against the appellant
4. Probability assessment based on similar cases
5. Overall risk level: Low / Medium / High

Be analytical and reference the case facts.{DISCLAIMER}"""


def generate_arguments(ctx: dict) -> str:
    return f"""You are NUC Legal AI, an intelligent legal assistant.

{_case_block(ctx)}

Task: Generate the strongest legal arguments that could be made FOR the appellant in this case.

Structure:
1. Primary argument (strongest legal ground)
2. Secondary arguments (supporting points)
3. Constitutional / statutory basis (cite the sections)
4. Precedent support (reference similar cases if available)
5. Counter-argument anticipation

Be specific, structured, and legally grounded.{DISCLAIMER}"""


def compare_cases(ctx: dict) -> str:
    sim = ctx.get("similar_cases", [])[:3]
    if not sim:
        return "No similar cases found in the dataset to compare."
    sim_block = "\n".join(
        f"Case {i+1} [{c['score']}% similarity]:\n{c['text'][:200]}"
        for i, c in enumerate(sim)
    )
    return f"""You are NUC Legal AI, an intelligent legal assistant.

{_case_block(ctx)}

Similar Cases Found:
{sim_block}

Task: Compare the current case with the similar cases above.

For each similar case:
1. Key similarities in legal issue and sections
2. Key differences in facts or outcome
3. What the similar case outcome suggests for the current case
4. Overall pattern across similar cases

Conclude with what the precedent pattern implies.{DISCLAIMER}"""


def eli5(ctx: dict) -> str:
    return f"""You are NUC Legal AI, an intelligent legal assistant.

{_case_block(ctx)}

Task: Explain this legal case as if explaining to a 12-year-old with no legal knowledge.

Use:
- Very simple words
- A short story-like format
- An analogy if helpful
- No legal jargon
- Maximum 6 sentences{DISCLAIMER}"""

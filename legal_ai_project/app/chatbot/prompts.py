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
    return f"""You are NUC Legal AI, a case-specific legal assistant. You are ONLY allowed to answer questions about the specific case that has been analyzed and provided in the context below.

{_case_block(ctx)}

User Question: {user_query}

STRICT RULES — you MUST follow these:
1. ONLY answer questions directly related to the case context above
2. If the question is about general law, general rights, other cases, or anything NOT in the case context — respond with: "I can only answer questions about the case currently being analyzed. Please ask something specific to this case."
3. Do NOT provide general legal education or textbook answers
4. Do NOT answer hypothetical questions unrelated to this case
5. Reference specific facts, sections, parties, and outcome from the case context
6. Keep your answer focused and concise — 3 to 5 sentences maximum
7. If the case context does not contain enough information to answer — say so clearly{DISCLAIMER}"""


def explain_case(ctx: dict) -> str:
    return f"""You are NUC Legal AI. Explain ONLY the specific case provided below — do not explain general law concepts.

{_case_block(ctx)}

Explain this specific case in simple language covering:
1. Who are the parties and what is the dispute
2. The specific legal issue in this case
3. Which sections of law were cited and why
4. What the court decided and the reasoning
5. What this outcome means for the parties

Stay strictly within the case facts above. Maximum 8 sentences.{DISCLAIMER}"""


def next_steps(ctx: dict) -> str:
    label = ctx.get("prediction")
    outcome = ctx.get("outcome", "")
    return f"""You are NUC Legal AI. Based ONLY on the case below, suggest next steps.

{_case_block(ctx)}

The ML model predicted outcome label: {label}, actual outcome: {outcome}

Suggest practical next steps SPECIFIC to this case:
1. Immediate actions for the appellant/petitioner in this case
2. Legal remedies available given this specific outcome
3. Key deadlines relevant to this type of case
4. What evidence or arguments could strengthen their position based on the sections cited

Do NOT give generic legal advice. Everything must relate to this specific case.{DISCLAIMER}"""


def risk_analysis(ctx: dict) -> str:
    return f"""You are NUC Legal AI. Analyze the legal risks in THIS specific case only.

{_case_block(ctx)}

Analyze:
1. Strength of the legal position based on the sections cited in this case
2. Key risks and weaknesses visible in this case's facts
3. What factors led to this specific outcome
4. How the similar cases above compare in terms of risk
5. Overall risk level for this case: Low / Medium / High — with justification

Base everything on the case context above. Do not generalize.{DISCLAIMER}"""


def generate_arguments(ctx: dict) -> str:
    return f"""You are NUC Legal AI. Generate legal arguments FOR the appellant based ONLY on this case.

{_case_block(ctx)}

Generate arguments using ONLY the facts, sections, and context above:
1. Primary argument — strongest ground from the sections cited
2. Secondary arguments — supporting points from the case facts
3. Constitutional or statutory basis — cite only sections present in this case
4. How the similar cases above support the appellant's position
5. Anticipated counter-arguments and how to address them

Do NOT introduce sections or precedents not mentioned in the case context.{DISCLAIMER}"""


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
    return f"""You are NUC Legal AI. Explain THIS specific case as if to a 12-year-old.

{_case_block(ctx)}

Explain only what happened in this case using:
- Very simple words
- A short story format about these specific parties
- What they were fighting about and what the court decided
- No legal jargon, no general law lessons
- Maximum 5 sentences{DISCLAIMER}"""


# ── Standalone chat (no case context) ────────────────────────────────────────

STANDALONE_QUERIES = {
    "general":  "Explain the general legal procedures in Indian courts.",
    "rights":   "What are the fundamental rights guaranteed under the Indian Constitution?",
    "bail":     "How does the bail process work in India? What are the types of bail?",
    "appeal":   "How do I file an appeal in an Indian court? What are the steps and timelines?",
    "eli5":     "Explain how the Indian court system works in very simple terms.",
    "explain":  "Give an overview of how Supreme Court judgments work in India.",
}


def standalone_query(user_query: str) -> str:
    return f"""You are Lincoln Lawyer, an expert AI Legal Assistant specializing in Indian law, \
the Indian Constitution, and Supreme Court judgments.

User Question: {user_query}

Instructions:
- Answer clearly and helpfully based on Indian law
- Use simple language unless the user asks for technical detail
- Structure your response with short paragraphs or numbered points
- Be accurate — do not fabricate laws or case citations
- If the question is outside Indian law, still help but note the limitation{DISCLAIMER}"""


# ── Lincoln Lawyer prompts — general legal assistant, no case context ─────────

_LINCOLN_SYSTEM = (
    "You are Lincoln Lawyer, an expert AI legal assistant specializing in Indian law, "
    "the Indian Constitution, and Supreme Court judgments. "
    "Answer legal questions clearly and helpfully. "
    "You may answer general legal questions about Indian law. "
    "Refuse only non-legal questions (math, science, general knowledge unrelated to law). "
    "Always append the disclaimer at the end."
)

_LINCOLN_DISCLAIMER = (
    "\n\n---\n⚠️ *This is general legal information only and does not constitute legal advice. "
    "Consult a qualified lawyer for your specific situation.*"
)


def lincoln_query(user_query: str) -> str:
    return (
        f"You are Lincoln Lawyer, an expert AI legal assistant for Indian law.\n\n"
        f"User question: {user_query}\n\n"
        f"Answer clearly and concisely. If the question is completely unrelated to law "
        f"(e.g. math, science, sports), politely decline and redirect to legal topics."
        f"{_LINCOLN_DISCLAIMER}"
    )


def lincoln_procedures() -> str:
    return (
        "Explain the key legal procedures a common person should know in India — "
        "filing an FIR, approaching a court, getting bail, filing a PIL, and appealing a judgment. "
        "Keep it practical and simple."
        f"{_LINCOLN_DISCLAIMER}"
    )


def lincoln_rights() -> str:
    return (
        "Explain the Fundamental Rights guaranteed by the Indian Constitution in simple language. "
        "Cover Articles 14-32 briefly and mention how citizens can enforce them."
        f"{_LINCOLN_DISCLAIMER}"
    )


def lincoln_bail() -> str:
    return (
        "Explain the bail process in India — types of bail (regular, anticipatory, interim), "
        "how to apply, what courts have jurisdiction, and key factors courts consider. "
        "Keep it practical."
        f"{_LINCOLN_DISCLAIMER}"
    )


def lincoln_appeal() -> str:
    return (
        "Explain how to file an appeal in India — from Sessions Court to High Court to Supreme Court. "
        "Cover timelines, grounds for appeal, and the SLP process under Article 136."
        f"{_LINCOLN_DISCLAIMER}"
    )


def lincoln_explain_prompt() -> str:
    return (
        "Give a brief overview of how Indian Supreme Court judgments work — "
        "how cases reach the Supreme Court, how judgments are structured, "
        "and what makes a judgment binding."
        f"{_LINCOLN_DISCLAIMER}"
    )


def lincoln_eli5_prompt() -> str:
    return (
        "Explain how the Indian court system works as if explaining to a 12-year-old. "
        "Use simple words and a story-like format. Cover: police → magistrate → sessions court "
        "→ high court → supreme court."
        f"{_LINCOLN_DISCLAIMER}"
    )

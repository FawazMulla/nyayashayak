# NUC Legal AI — System Context

This document is the single reference for understanding every feature, component,
data flow, and configuration point in the project. Read this before making changes.

---

## 1. What the System Does

NUC Legal AI is a Django web application that:
1. Accepts Indian Supreme Court judgment PDFs or raw text
2. Extracts structured fields (parties, sections, outcome, category, date)
3. Runs AI correction on extracted fields via Cohere
4. Predicts case outcome (Allowed / Dismissed) using a trained ML model
5. Finds semantically similar past cases using InLegalBERT embeddings
6. Provides an AI chatbot (Lincoln Lawyer) powered by OCI Generative AI

---

## 2. Pages & Routes

| URL | View | Template | Purpose |
|-----|------|----------|---------|
| `/` | `upload_case` | `upload.html` | Home — upload PDF or paste text |
| `/analyze/` | `analyze_case` | `result.html` | POST — runs full pipeline, shows results |
| `/chat/` | `lincoln_lawyer` | `chat.html` | Lincoln Lawyer — standalone legal chatbot |
| `/chatbot/` | `chatbot_api` | — | AJAX POST — returns JSON chatbot response |
| `/admin/` | Django admin | — | Admin panel |

---

## 3. Feature Breakdown

### 3.1 PDF / Text Extraction (`app/extractor.py`)

Accepts a PDF file or raw text string. Extracts:

| Field | Method |
|-------|--------|
| `appellant` / `respondent` | Parsed from filename pattern `Name_vs_Name_on_Date` |
| `judgment_date` | Regex on signature block (after "NEW DELHI") |
| `case_number` | Regex on first 1500 chars (CRIMINAL/CIVIL APPEAL NO.) |
| `case_id` | INSC citation e.g. `2025 INSC 35` |
| `sections` | Multi-pass regex against 40+ known Acts |
| `outcome` | Regex on last 4000 chars against priority-ordered patterns |
| `category` | Regex on first 2000 chars (Criminal, Civil, SLP, Tax, etc.) |
| `input_text` | Clean 150-300 word prose built from facts + reasoning + decision |
| `label` | `1` = Allowed, `0` = Dismissed, `None` = excluded |

Text extraction priority: pdfminer.six (primary) → pdfplumber (fallback).

---

### 3.2 AI Field Correction (`app/correction.py`)

Uses Cohere (`command-a-03-2025`) via `COHERE_API_KEY`.

Pipeline:
1. `is_legal_document(text)` — validates the document is a real court judgment (requires 4+ court-specific signals, 100+ words). Rejects random PDFs.
2. `detect_issues(data, text)` — rule-based check for known extraction errors (wrong section format, garbled appellant name, wrong category).
3. `run_ai_pipeline(data, text)` — single Cohere call that returns both:
   - `summary` — 4-6 sentence plain-English case summary (stored as `ai_summary`)
   - `corrections` — fixed values for any flagged fields
4. `hybrid_correction(data, text)` — orchestrates the above, merges corrections into result dict.

Toggle: `AI_CORRECTION_ENABLED=true|false` in `.env`

---

### 3.3 ML Outcome Prediction (`app/ml/classifier.py`)

Model: Logistic Regression trained on InLegalBERT embeddings.

- Input: `input_text` string from extractor
- Output: `label` (0 or 1) + `confidence` (float 0-1)
- Model file: `data/model.pkl` (built by `build_ml` command)
- Falls back gracefully if model not built yet

---

### 3.4 Embeddings (`app/ml/embeddings.py`)

Model: `law-ai/InLegalBERT` (768-dim BERT fine-tuned on Indian legal text).

- `get_embedding(text)` — single text → numpy array (768,)
- `get_embeddings_batch(texts)` — batch processing for dataset
- `save_dataset_embeddings(texts)` — saves to `data/embeddings.npy` + `data/embeddings_meta.npy`
- `load_dataset_embeddings()` — loads from disk

Model location priority:
1. `legal_ai_project/models/InLegalBERT/` (local, fast)
2. HuggingFace Hub auto-download (fallback, requires internet)

---

### 3.5 Similarity Search (`app/ml/similarity.py`)

Finds semantically similar past cases from the 400-judgment dataset.

Algorithm: Mean-centered cosine similarity
- Subtracts dataset mean embedding before computing similarity
- This removes the shared "legal vocabulary" component so similarity reflects actual case content, not just shared legal terms
- Valid score range: `[0.05, 0.75]` mapped to `[0, 100]%` for display
- Returns top 5 results by default

---

### 3.6 Chatbot — Case Mode (`app/chatbot/`)

Activated after a case is analyzed. Stored in Django session (`case_context`).

System prompt: `CASE_SYSTEM` in `prompt_config.py`

Quick actions (buttons):
| Action key | What it does |
|------------|-------------|
| `explain` | Plain-language case explanation |
| `nextsteps` | Practical next steps for the appellant |
| `risk` | Risk assessment with Low/Medium/High rating |
| `arguments` | Strongest legal arguments for the appellant |
| `compare` | Comparison with similar cases |
| `eli5` | Explain like I'm 5 |

Free-text questions are filtered by `_is_case_related()` — off-topic queries get a static rejection reply without calling the AI.

---

### 3.7 Chatbot — Lincoln Lawyer Mode (`app/chatbot/`)

Standalone general Indian law assistant. Accessible at `/chat/` without uploading a case.

System prompt: `LINCOLN_SYSTEM` in `prompt_config.py`

Quick actions:
| Action key | What it does |
|------------|-------------|
| `general` | Key legal procedures in India |
| `rights` | Fundamental Rights (Articles 14-32) |
| `bail` | Bail process and types |
| `appeal` | How to file an appeal |
| `explain` | How Supreme Court judgments work |
| `eli5` | Indian court system for beginners |

Free-text questions accepted for any Indian law topic.

---

### 3.8 OCI Generative AI Client (`app/chatbot/chatbot.py`)

Both chatbot modes use OCI Generative AI via the `oci` Python SDK.

- Auth: API key file (`key_file`) configured via `.env`
- Model: configurable via `OCI_CHAT_MODEL_ID` (default: `cohere.command-a-03-2025`)
- Request type: `CohereChatRequest` for Cohere models, `GenericChatRequest` for Llama/others
- `max_tokens`: 300 (keeps responses concise, reduces latency)
- `temperature`: 0.2 (consistent, professional tone)
- Client is a singleton — initialized once, reused across requests
- `_init_attempted` flag prevents repeated failed init attempts

---

## 4. Data Flow (Full Pipeline)

```
User uploads PDF / pastes text
        │
        ▼
extract_text_from_pdf()          ← pdfminer → pdfplumber fallback
        │
        ▼
is_legal_document()              ← rejects non-judgment documents
        │
        ▼
extract_fields()                 ← sections, outcome, category, date, etc.
        │
        ▼
hybrid_correction()              ← Cohere: AI summary + field corrections
        │
        ▼
predict()                        ← InLegalBERT + LogReg → label + confidence
        │
        ▼
find_similar()                   ← mean-centered cosine → top 5 similar cases
        │
        ▼
save_to_dataset()                ← appends to data/processed.csv + processed.json
        │
        ▼
request.session["case_context"]  ← stored for chatbot use
        │
        ▼
result.html                      ← displays all results + chatbot panel
```

---

## 5. Configuration (`.env`)

| Variable | Used by | Purpose |
|----------|---------|---------|
| `COHERE_API_KEY` | `correction.py` | Cohere client for AI field correction + summary |
| `AI_CORRECTION_ENABLED` | `correction.py` | Toggle AI correction on/off |
| `CHATBOT_ENABLED` | `chatbot.py` | Toggle chatbot on/off |
| `OCI_USER_OCID` | `chatbot.py` | OCI user identifier |
| `OCI_TENANCY_OCID` | `chatbot.py` | OCI tenancy identifier |
| `OCI_FINGERPRINT` | `chatbot.py` | API key fingerprint |
| `OCI_PRIVATE_KEY_PATH` | `chatbot.py` | Path to `.pem` private key file |
| `OCI_REGION` | `chatbot.py` | OCI region (e.g. `us-chicago-1`) |
| `OCI_COMPARTMENT_ID` | `chatbot.py` | OCI compartment for GenAI billing |
| `OCI_CHAT_MODEL_ID` | `chatbot.py` | Model ID (e.g. `cohere.command-a-03-2025`) |

---

## 6. Prompt Configuration (`app/chatbot/prompt_config.py`)

All AI prompts live in one file. Edit here to change AI behavior — no other files need touching.

| Constant | Controls |
|----------|---------|
| `DISCLAIMER` | Warning appended to every case-mode response |
| `RESPONSE_STYLE` | Output format rules for all case-mode responses |
| `CASE_SYSTEM` | AI personality and rules in case analysis mode |
| `OFF_TOPIC_REPLY` | Static reply for off-topic questions (AI not called) |
| `CASE_EXPLAIN` | "Explain Case" button prompt |
| `CASE_NEXT_STEPS` | "Next Steps" button prompt |
| `CASE_RISK` | "Risk Analysis" button prompt |
| `CASE_ARGUMENTS` | "Generate Arguments" button prompt |
| `CASE_COMPARE` | "Compare Cases" button prompt |
| `CASE_ELI5` | "ELI5" button prompt |
| `CASE_QUERY` | Free-text question prompt in case mode |
| `LINCOLN_SYSTEM` | AI personality and rules in Lincoln Lawyer mode |
| `LINCOLN_STYLE` | Output format rules for Lincoln mode |
| `LINCOLN_DISCLAIMER` | Warning appended to Lincoln mode responses |
| `LINCOLN_QUERY` | Free-text question prompt in Lincoln mode |
| `LINCOLN_PROCEDURES` | "Legal Procedures" button prompt |
| `LINCOLN_RIGHTS` | "Fundamental Rights" button prompt |
| `LINCOLN_BAIL` | "Bail Process" button prompt |
| `LINCOLN_APPEAL` | "File an Appeal" button prompt |
| `LINCOLN_EXPLAIN` | "How SC Judgments Work" button prompt |
| `LINCOLN_ELI5` | "Court System ELI5" button prompt |

---

## 7. Management Commands

```bash
# Build embeddings + train classifier (run after adding new data)
python manage.py build_ml

# Embeddings only
python manage.py build_ml --embed-only

# Train classifier only (embeddings already exist)
python manage.py build_ml --train-only
```

Source: `app/management/commands/build_ml.py`

---

## 8. Data Files (`data/`)

| File | Generated by | Contents |
|------|-------------|---------|
| `processed.csv` | `save_to_dataset()` on each analysis | case_id, input_text, label, category, outcome, sections |
| `processed.json` | `save_to_dataset()` on each analysis | Same as CSV in JSON format |
| `embeddings.npy` | `build_ml` command | Float32 array (N × 768) — InLegalBERT embeddings |
| `embeddings_meta.npy` | `build_ml` command | Object array of input_text strings (index matches embeddings) |
| `model.pkl` | `build_ml` command | Trained Logistic Regression classifier (joblib) |

---

## 9. Key Design Decisions

- Two separate API keys: `COHERE_API_KEY` for extraction/correction, OCI for chatbot. They never share a client.
- Session-based case context: case data is stored in Django session after analysis, chatbot reads from there — no database needed.
- Off-topic filter runs before the AI call in case mode — saves latency and API cost for irrelevant questions.
- Mean-centered similarity: raw cosine on legal text is noisy because all judgments share vocabulary. Centering removes the shared component.
- Single Cohere call for correction: summary + field corrections are requested in one prompt to minimize API usage.
- `_init_attempted` flag on OCI client: prevents the app from retrying a failed client init on every request.

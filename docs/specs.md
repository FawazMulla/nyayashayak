# NUC Legal AI — Full Application Specification

## Overview

NUC Legal AI is a Django web application that analyzes Indian Supreme Court judgments. It accepts PDF uploads or raw text, extracts structured legal fields, runs AI-powered correction and summarization, predicts case outcomes using a trained ML model, finds semantically similar past cases, and provides an AI chatbot for legal assistance.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django 6.0.4 |
| Database | PostgreSQL (via dj-database-url) |
| WSGI Server | Gunicorn 25.3.0 |
| Static Files | WhiteNoise 6.12.0 |
| PDF Extraction | pdfminer.six + pdfplumber (fallback) |
| ML Embeddings | InLegalBERT (law-ai/InLegalBERT, 768-dim BERT) |
| ML Classifier | Scikit-learn VotingClassifier (Calibrated SVM + Logistic Regression) |
| AI Correction | Cohere SDK v6 (command-a-03-2025) |
| AI Chatbot | OCI Generative AI SDK (cohere.command-a-03-2025) |
| Deep Learning | PyTorch 2.11.0 (CPU), Transformers 5.5.3 |
| Numerical | NumPy 2.4.4, SciPy 1.17.1 |
| Model Persistence | Joblib 1.5.3 |
| Frontend | Vanilla JS, Bootstrap Icons, custom CSS |
| Deployment | Render (Git LFS for 509MB model binary) |

---

## Application Features

### 1. Case Upload & Analysis

Users can submit a case in two ways:
- Upload a PDF file (Indian Supreme Court judgment)
- Paste raw judgment text directly

The full analysis pipeline runs on submission and produces:
- Extracted structured fields (parties, date, case number, sections, outcome, category)
- AI-generated plain-English summary (via Cohere)
- ML outcome prediction with confidence score
- Top 5 semantically similar past cases
- A chatbot panel pre-loaded with the case context

**Route**: `POST /analyze/`  
**View**: `analyze_case`  
**Template**: `result.html`

---

### 2. PDF Text Extraction

**File**: `app/extractor.py`

Text extraction uses a two-stage pipeline:
1. **pdfminer.six** (primary) — layout-aware extraction with tuned `LAParams` for Indian Kanoon PDFs
2. **pdfplumber** (fallback) — used if pdfminer returns empty output

After extraction, the text is deep-cleaned: binary artifacts, digital signature blocks, page numbers, judge name lines, paragraph numbering, footnote superscripts, and OCR noise are all stripped.

---

### 3. Field Extraction

**File**: `app/extractor.py`

| Field | Method |
|---|---|
| `appellant` / `respondent` | Parsed from filename pattern `Name_vs_Name_on_Date`, refined from text header |
| `judgment_date` | Regex on last 1000 chars, prioritizes date after "NEW DELHI" |
| `case_number` | Regex on first 1500 chars (CRIMINAL/CIVIL APPEAL NO., WRIT PETITION, SLP, etc.) |
| `case_id` | INSC citation regex (e.g. `2025 INSC 35`) |
| `sections` | Multi-pass regex against 40+ known Acts (IPC, CrPC, BNS, NDPS, PMLA, etc.) |
| `outcome` | Priority-ordered regex on last 4000 chars (Allowed, Dismissed, Disposed, Acquitted, Quashed, Remanded, etc.) |
| `category` | Regex on first 2000 chars (Criminal, Civil, SLP, Tax, Service Law, Family Law, etc.) |
| `input_text` | 150–300 word clean prose: 2 facts sentences + 1–2 reasoning sentences + sections. Verdict sentences are stripped before inclusion (see `strip_verdict_signals`). |
| `label` | `1` = Allowed, `0` = Dismissed, `None` = excluded (Disposed, Partly Allowed, Unknown) |

---

### 4. Legal Document Validation

**File**: `app/correction.py` — `is_legal_document()`

Before any processing, the document is validated as a genuine court judgment. It must:
- Contain at least 100 words
- Match at least 4 of 20+ court-specific signal patterns (appellant, respondent, Hon'ble, INSC, Criminal Appeal, Writ Petition, etc.)

Random PDFs, invoices, or non-legal documents are rejected with a user-facing error.

---

### 5. AI Field Correction & Summary

**File**: `app/correction.py`

A single Cohere API call (`command-a-03-2025`) handles both tasks:
1. **Field correction** — fixes known extraction errors (wrong section format, garbled appellant name, wrong category)
2. **AI summary** — 4–6 sentence plain-English summary of the case

The rule-based `detect_issues()` check runs first. If no issues are found, the AI call is skipped entirely (saves API cost). The summary is always requested.

Toggle: `AI_CORRECTION_ENABLED` (database toggle via `AISettings` model, falls back to env var)

---

### 6. ML Outcome Prediction

**File**: `app/ml/classifier.py`

- Model: VotingClassifier ensemble — Calibrated LinearSVC (isotonic) weighted 2x + LogisticRegression weighted 1x
- Input: `input_text` string (verdict-stripped) → InLegalBERT embedding (768-dim)
- Output: `label` (0 = Dismissed, 1 = Allowed) + calibrated `confidence` (float 0–1)
- Calibration: `CalibratedClassifierCV` with isotonic regression on SVM — probabilities are well-calibrated
- Decision threshold: `P(Allowed) >= 0.62` (raised from 0.5 to compensate for 79:21 class imbalance)
- 5-fold stratified cross-validation runs during `build_ml` — real accuracy printed and saved to `data/model_meta.json`
- CV accuracy: **93.4% ± 2.6%** on 394 training samples (after verdict stripping)
- Model file: `data/model.pkl` (joblib)
- Metadata file: `data/model_meta.json` — stores cv_accuracy_mean, cv_accuracy_std, cv_scores, train_samples, class_counts, model_type
- Singleton pattern: loaded once, reused across requests
- Graceful fallback: if model not built, prediction is skipped and a rule-based confidence estimate is shown

---

### 7. InLegalBERT Embeddings

**File**: `app/ml/embeddings.py`

- Model: `law-ai/InLegalBERT` (BERT fine-tuned on Indian legal text, 768-dim)
- Local path: `legal_ai_project/models/InLegalBERT/`
- Singleton: tokenizer and model load once, reused across all requests
- `get_embedding(text)` → numpy array (768,) via mean pooling over token dimension
- `get_embeddings_batch(texts, batch_size=16)` → numpy array (N, 768)
- `save_dataset_embeddings(texts, meta_records)` → saves `data/embeddings.npy`, `data/embeddings_meta.npy`, and `data/similarity_meta.json`
- `meta_records`: list of dicts with `case_id`, `outcome`, `category`, `sections` per entry — used by similarity search for rich result display
- Max token length: 512

---

### 8. Similarity Search

**File**: `app/ml/similarity.py`

Finds the top 5 semantically similar past cases from the dataset using mean-centered cosine similarity.

**Algorithm**:
1. Compute dataset mean embedding and subtract from all vectors (removes shared "legal vocabulary" component)
2. L2-normalize the centered vectors
3. Center and normalize the query embedding using the same dataset mean
4. Compute vectorized cosine similarity (matrix multiply)
5. Filter scores to valid range `[0.05, 0.75]` (below = unrelated, above = near-duplicate)
6. Map valid range to `[0, 100]%` for display

Near-duplicates (score ≥ 0.999) are excluded. Returns up to 5 results.

Each result dict now contains:
- `text` — input_text snippet (300 chars)
- `score` — similarity percentage [0–100]
- `case_id` — INSC citation (e.g. "2025 INSC 35")
- `outcome` — extracted outcome (Allowed / Dismissed / Disposed etc.)
- `category` — case category (Criminal, Civil, etc.)
- `sections` — cited legal sections

Rich metadata is loaded from `data/similarity_meta.json` (built by `build_ml`). Falls back to text-only if file not present.

---

### 9. Chatbot — Case Mode

**Files**: `app/chatbot/chatbot.py`, `app/chatbot/prompts.py`, `app/chatbot/prompt_config.py`

Activated after a case is analyzed. Case context is stored in the Django session (`case_context` key). The chatbot reads from session — no database query needed per message.

**Quick action buttons**:

| Action | Description |
|---|---|
| `explain` | Plain-language case explanation |
| `nextsteps` | Practical next steps for the appellant |
| `risk` | Risk assessment with Low/Medium/High rating |
| `arguments` | Strongest legal arguments for the appellant |
| `compare` | Comparison with similar cases |
| `eli5` | Explain like I'm 5 |

Free-text questions are accepted for anything related to the case or Indian law. Completely off-topic questions (math, sports, cooking) get a static rejection reply — the AI is not called.

---

### 10. Chatbot — Lincoln Lawyer Mode

**Route**: `GET /chat/`  
**View**: `lincoln_lawyer`

Standalone general Indian law assistant. No case upload required. Accessible directly from the navigation.

**Quick action buttons**:

| Action | Description |
|---|---|
| `general` | Key legal procedures in India (FIR, bail, PIL, appeals) |
| `rights` | Fundamental Rights under the Indian Constitution (Articles 14–32) |
| `bail` | Bail process, types, jurisdiction, what courts consider |
| `appeal` | How to file an appeal (Sessions → High Court → Supreme Court, SLP) |
| `explain` | How Supreme Court judgments work |
| `eli5` | Indian court system explained for beginners |

Free-text questions accepted for any Indian law topic.

---

### 11. OCI Generative AI Client

**File**: `app/chatbot/chatbot.py`

Both chatbot modes use OCI Generative AI via the `oci` Python SDK.

- Auth: API key file (`OCI_PRIVATE_KEY_PATH`)
- Model: configurable via `OCI_CHAT_MODEL_ID` (default: `cohere.command-a-03-2025`)
- Request type: `CohereChatRequest` with `preamble_override` for system prompt
- `max_tokens`: 500 (concise responses, reduced latency)
- `temperature`: 0.3 (consistent, professional tone)
- Singleton client with `_init_attempted` flag — prevents repeated failed init attempts on every request
- Conversation history: last 8 messages (4 exchanges) from DB passed on every call — chatbot remembers prior context within the session
- Toggle: `CHATBOT_ENABLED` (database toggle via `AISettings`, falls back to env var)

---

### 12. Prompt Configuration

**File**: `app/chatbot/prompt_config.py`

All AI prompts are centralized in one file. No other files need to be touched to change AI behavior.

| Constant | Controls |
|---|---|
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

## Data Flow (Full Pipeline)

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
hybrid_correction()              ← Cohere: AI summary + field corrections (1 call)
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

## Database Models

### User
Custom `AbstractUser` with:
- `role`: `case_analyzer` | `lincoln_lawyer` | `both`
- `is_approved`: boolean — accounts are inactive until admin approves
- `can_analyze()` / `can_chat()` helper methods

### AISettings
Singleton model (pk=1) for runtime AI toggles:
- `cohere_enabled`: toggles Cohere correction pipeline
- `oci_enabled`: toggles OCI chatbot

### UploadedCase
- FK to `User`
- `file`: FileField (stored under `media/uploads/<uuid>/`)
- `filename`: original filename

### ChatSession
- FK to `User`, optional FK to `UploadedCase`
- `mode`: `case` | `lincoln`
- `title`: auto-set from appellant name or first message
- Ordered by `-updated_at`

### ChatMessage
- FK to `ChatSession`
- `sender`: `user` | `ai`
- `message`: TextField
- Ordered by `created_at`

---

## URL Routes

| URL | View | Purpose |
|---|---|---|
| `/` | `landing` | Landing page (redirects to dashboard if logged in) |
| `/upload/` | `upload_case` | Case upload form |
| `/analyze/` | `analyze_case` | POST — runs full pipeline |
| `/chat/` | `lincoln_lawyer` | Lincoln Lawyer standalone chatbot |
| `/chatbot/` | `chatbot_api` | AJAX POST — returns JSON chatbot response |
| `/auth/register/` | `register_view` | User registration |
| `/auth/login/` | `login_view` | Login (blocks unapproved accounts) |
| `/auth/logout/` | `logout_view` | Logout |
| `/auth/profile/` | `profile_view` | User profile |
| `/dashboard/` | `dashboard` | User dashboard |
| `/admin-panel/` | `admin_panel` | Admin: approve/reject users, set roles, system reset |
| `/ai-config/` | `ai_config` | Admin: toggle Cohere/OCI on/off |
| `/history/` | `chat_history` | List all chat sessions |
| `/history/<id>/` | `chat_session_view` | View a specific chat session |
| `/download/<case_id>/` | `download_case` | Download uploaded PDF |

---

## Authentication & Authorization

- Custom `User` model with `is_approved` flag
- New registrations are set `is_active=False`, `is_approved=False` — blocked until admin approves
- Admin approval sends an email notification to the user
- Admin rejection also sends an email
- `upload_case` and `lincoln_lawyer` views redirect unapproved users to dashboard
- Admin panel (`/admin-panel/`) is staff-only
- AI config (`/ai-config/`) is staff-only
- System reset (from admin panel) deletes all non-superuser accounts, sessions, messages, and uploaded files

---

## Management Commands

```bash
# Build embeddings + train classifier (run after adding new data)
python manage.py build_ml

# Embeddings only
python manage.py build_ml --embed-only

# Train classifier only (embeddings already exist)
python manage.py build_ml --train-only
```

**Source**: `app/management/commands/build_ml.py`

Reads `data/processed.csv`, generates InLegalBERT embeddings for all `input_text` rows, saves to `data/embeddings.npy` + `data/embeddings_meta.npy` + `data/similarity_meta.json` (rich metadata per entry), then trains and saves the ensemble classifier to `data/model.pkl` + `data/model_meta.json`.

---

## Data Files

| File | Generated by | Contents |
|---|---|---|
| `data/processed.csv` | `save_to_dataset()` on each analysis | case_id, input_text (verdict-stripped), label, category, outcome, sections |
| `data/processed.json` | `save_to_dataset()` on each analysis | Same as CSV in JSON format |
| `data/embeddings.npy` | `build_ml` command | Float32 array (N × 768) — InLegalBERT embeddings |
| `data/embeddings_meta.npy` | `build_ml` command | Object array of input_text strings (index matches embeddings) |
| `data/similarity_meta.json` | `build_ml` command | List of dicts: case_id, outcome, category, sections per entry |
| `data/model.pkl` | `build_ml` command | Trained VotingClassifier ensemble (joblib) |
| `data/model_meta.json` | `build_ml` command | CV accuracy, per-fold scores, class counts, model type |

---

## Frontend

**Templates** (`legal_ai_project/templates/`):
- `base.html` — navigation + layout shell
- `landing.html` — public landing page
- `upload.html` — PDF upload + text paste with pipeline indicator
- `result.html` — full case analysis dashboard (summary, extracted fields, ML prediction, similar cases, chatbot panel)
- `chat.html` — Lincoln Lawyer standalone chatbot
- `dashboard.html` — user dashboard
- `admin_panel.html` — user approval, role assignment, system reset
- `ai_config.html` — toggle AI features on/off
- `chat_history.html` — list past chat sessions
- `chat_session.html` — view a specific session
- `auth/register.html`, `auth/login.html`, `auth/profile.html`

**Static files** (`legal_ai_project/static/`):
- `css/base.css` — global styles
- `css/upload.css` — upload page styles
- `css/result.css` — result page styles
- `css/chat.css` — chatbot styles
- `js/upload.js` — drag-and-drop PDF upload
- `js/result.js` — modal/toggle interactions on result page
- `js/chatbot.js` — AJAX chat message handling

---

## Deployment (Render)

**Procfile**: `web: gunicorn legal_ai_project.wsgi --log-file -`

**Build command**:
```
pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate
```

**Git LFS**: `pytorch_model.bin` (509MB) is tracked via Git LFS. GitHub provides 1GB free LFS storage.

**Persistent Disk**: Mount at `/opt/render/project/src/legal_ai_project/media` to preserve uploaded PDFs across deploys.

**After first deploy** — create superuser via Render shell:
```bash
python manage.py createsuperuser
```

---

## Key Design Decisions

- Two separate API clients: Cohere for extraction/correction, OCI for chatbot — they never share a client or key
- Session-based case context: case data stored in Django session after analysis, chatbot reads from there — no DB query per message
- Off-topic filter runs before the AI call in case mode — saves latency and API cost for irrelevant questions
- Mean-centered similarity: raw cosine on legal text is noisy because all judgments share vocabulary; centering removes the shared component
- Single Cohere call for correction: summary + field corrections requested in one prompt to minimize API usage
- `_init_attempted` flag on OCI client: prevents the app from retrying a failed client init on every request
- Singleton pattern for ML models: InLegalBERT and classifier load once at first request, reused for all subsequent requests
- Graceful ML fallbacks: if model files are not built, the app still works — ML features are simply skipped
- Verdict stripping before ML: `strip_verdict_signals()` removes outcome sentences from `input_text` before training and inference — prevents data leakage where the model reads the answer from the verdict sentence
- Calibrated decision threshold: `P(Allowed) >= 0.62` instead of 0.5 — compensates for 79:21 class imbalance, reduces false "Favorable" predictions on ambiguous cases
- Conversation memory in chatbot: last 8 DB messages passed as `chat_history` to OCI on every call — chatbot maintains context across turns
- Dataset deduplication: `save_to_dataset()` checks `case_id` before writing — same case never added twice


---

## Prompt Builder

**File**: `app/chatbot/prompts.py`

Thin adapter layer between `chatbot.py` and `prompt_config.py`. All prompt strings live in `prompt_config.py` — this file only assembles the runtime context block and calls the right template.

`_case_block(ctx)` builds the structured case context string injected into every case-mode prompt:
- AI summary (preferred) or rule-based input_text as the primary case description
- Appellant, category, outcome, sections
- ML prediction label + confidence
- Up to 3 similar cases with score, outcome badge, and category tag

All prompt builder functions (`explain_case`, `next_steps`, `risk_analysis`, `generate_arguments`, `compare_cases`, `eli5`, `lincoln_query`, etc.) simply format the config constants with the runtime context.

---

## Django Admin

**File**: `app/admin.py`

All models are registered with the Django admin site with custom configurations:

| Model | Admin features |
|---|---|
| `User` | List display with role/approval status, inline editable `is_approved`/`is_active`/`role`, bulk approve/reject/reset actions |
| `AISettings` | Shows Cohere and OCI toggle states |
| `ChatSession` | Filterable by mode, raw_id for user FK |
| `ChatMessage` | Filterable by sender |
| `UploadedCase` | Shows filename, user, upload time |

Admin bulk actions:
- "Approve selected users" — sets `is_approved=True`, `is_active=True`
- "Reject / deactivate selected users" — sets both to False
- "RESET SYSTEM" — deletes all non-superuser users + all chat/file data, logs the action

---

## JavaScript Modules

### chatbot.js

Shared across `result.html` (case mode) and `chat.html` (Lincoln mode). Reads `window.CSRF_TOKEN`, `window.CHATBOT_URL`, and `window.CHATBOT_MODE` set inline by each template.

Key functions:
- `Chatbot.init(welcomeMsg)` — appends welcome message, binds Enter key, auto-resizes textarea
- `Chatbot.send(inputId)` — reads input, appends user bubble, POSTs to `/chatbot/`, appends AI response with typewriter effect
- `Chatbot.quickAction(action)` — appends a display label as user bubble, POSTs with action key
- `postToBot(query, action)` — shows typing indicator, fetches `/chatbot/`, removes indicator on response
- `typewriterAppend(bubble, text, speed)` — types AI response character by character at 10ms/char; HTML tags are skipped instantly so markdown renders correctly
- `renderMarkdown(text)` — converts `**bold**`, `*italic*`, `` `code` ``, `- bullets`, numbered lists to HTML — no external library
- Typing indicator: three animated dots shown while waiting for response

### result.js

- Verdict hero entrance animation: scale+fade on page load (120ms delay)
- Animates confidence bar (`conf-bar`) to `window.CONF_PCT` on load
- Animates confidence ring SVG stroke-dashoffset to `window.CONF_PCT` on load
- Animates similarity score bars on load
- `toggleBlock(id)` — collapses/expands dashboard sections
- `openModal(id)` / `closeModal(id)` / `closeModalOutside(e, id)` — modal overlay management
- Escape key closes all open modals
- `shareResult()` — copies formatted case summary to clipboard (Ctrl+Shift+S)
- `printResult()` — triggers `window.print()` for PDF export (Ctrl+Shift+P)
- Risk meter: rule-based score computed from ML confidence + outcome label + section count; animates colored bar (green/amber/red) with Low/Medium/High label

### upload.js

- Canvas particle animation: 120 floating particles + grid lines on the background canvas, runs on all pages via `base.html`
- `switchTab(name, btn)` — toggles between PDF upload and text paste tabs
- Drag-and-drop zone: handles `dragover`, `dragleave`, `drop` events, updates `DataTransfer` on file drop
- Form submit validation: checks file selected (PDF tab) or minimum word count (text tab)
- Pipeline overlay animation: cycles through 6 stages with realistic timing; shows "Finalizing results…" after animation completes while server finishes
- Clears overlay on `pageshow` (handles back-button and error reloads)

---

## Templates

### base.html

Global layout shell. Includes:
- Google Fonts (Inter + Inconsolata)
- Bootstrap Icons CDN
- `base.css`
- Background canvas (`bg-canvas`) — particle animation runs on all pages
- Navigation bar with conditional links based on `user.is_authenticated`, `user.is_approved`, `user.is_staff`
- Nav items: Dashboard, Analyze, Lincoln Lawyer (approved users), Users, AI Config (staff only)
- `upload.js` loaded globally (drives the canvas animation)

### upload.html (extends base.html)

- Pipeline step indicator (Upload → Extract → Validate → AI Correct → ML Predict → Results)
- Two-tab input: PDF drag-and-drop zone or text paste textarea
- Animated pipeline overlay modal shown on form submit — cycles through 6 stages with timing:
  - Text Extraction (1800ms), Legal Validation (900ms), Field Extraction (1200ms), AI Correction (2800ms), ML Prediction (1400ms), Similarity Search (1000ms)
- Progress bar fills as stages complete
- Feature badge row at bottom (Outcome Classification, Category Detection, Section Extraction, AI Correction, ML Confidence)

### result.html

Full analysis dashboard with two-column layout. Does not extend `base.html` (standalone template with its own nav).

Left column:
- Verdict hero card (green/red/neutral based on ML label) with outcome display and animated confidence ring (SVG stroke-dashoffset). Entrance animation: scale+fade on load.
- Insight cards row: Category, Judgment Date, Word Count
- AI Case Summary block (collapsible, expandable to modal) — shows Cohere summary or rule-based input_text. Copy-to-clipboard button.
- Case Narrative block — structured Facts → Legal Context → Outcome flow derived from extracted fields (no AI call)
- Extracted Information block (collapsible, expandable to modal) — case ID, number, parties, outcome, category, sections as pills
- ML Insights block — outcome, prediction, source, animated confidence bar, CV accuracy badge, training sample count
- Risk Assessment block — rule-based risk meter (Low/Medium/High) computed from confidence + outcome + section count
- Similar Cases block — top 3 shown inline with outcome badges (green Allowed / red Dismissed), category, score bars. "All" button opens modal with all 5 including case_id and sections.
- System Info block (collapsed by default) — tech stack tags

Right column (sticky chatbot panel):
- Lincoln Lawyer header with gradient background and pulsing online indicator
- Case context banner showing appellant name and outcome
- 6 quick action buttons in 3×2 grid (Explain, Next Steps, Risk, Arguments, Compare, ELI5)
- Chat message area with typewriter effect and markdown rendering
- Text input with send button

Nav bar: Share button (copies formatted summary), PDF button (triggers print), New Analysis link.

Three modals: Summary, Extracted Info, Similar Cases (all closeable via X button, outside click, or Escape key).

JS variables injected inline: `CONF_PCT`, `RESULT_LABEL`, `RESULT_APPELLANT`, `RESULT_OUTCOME`, `RESULT_CONFIDENCE`, `RESULT_CATEGORY`, `RESULT_SECTIONS`.

### chat.html (extends base.html)

Lincoln Lawyer standalone page:
- Custom SVG balance scales avatar
- 6 quick action buttons with inline SVG icons (Legal Procedures, Fundamental Rights, Bail Process, Filing Appeal, Explain a Case, ELI5)
- Buttons animate in with staggered `qbtnAppear` keyframe
- Auto-resizing textarea input (max 120px height)
- Disclaimer footer: "Lincoln Lawyer provides general legal information, not legal advice."
- Welcome message on init

### dashboard.html (extends base.html)

- Welcome message with username
- Pending approval banner for unapproved users
- Stats strip (approved users only): Cases Analyzed, Chat Sessions, Dataset Size — all with animated number counters (count up from 0 on load)
- Outcome distribution tile: Allowed vs Dismissed counts with animated bar
- Category distribution panel: top 4 case categories with animated CSS bar charts (from `processed.json`)
- AI Stack status panel: shows InLegalBERT, Cohere, OCI, Similarity Search status
- CTA hero card for new users with zero cases/sessions
- Feature cards grid: Case Analyzer, Lincoln Lawyer, Chat History, User Management, AI Config (shown based on role/staff status)
- Recent activity list: last 6 chat sessions with mode icon, title, timestamp, message count, attached file name
- Quick actions sidebar: jump links to Analyze, Lincoln Lawyer, Continue Last Session, View History, Profile
- `total_dataset`, `category_counts` context variables passed from view

### landing.html (extends base.html)

Public marketing page:
- Hero section: headline, subtext, Get Started / Login CTAs, stats (400+ judgments, 85% ML accuracy, 768-dim InLegalBERT, 3 AI models)
- Stats bar: Access model, AI stack, ML model
- Features grid (6 cards with custom SVGs): Case Analyzer, Lincoln Lawyer, ML Outcome Prediction, AI Field Correction, Case Context Chatbot, Role-Based Access
- Pipeline section: 5-step "How it Works" (Upload → Extract → AI Correct → ML Predict → Results)
- Footer: brand name, tagline, tech stack

### auth templates

- `register.html` — username, email, role selector, password fields
- `login.html` — username/password, shows error for invalid credentials or unapproved accounts
- `profile.html` — displays username, email, role, approval status

### registration templates (Django built-in password reset flow)

- `password_reset_form.html` — email input
- `password_reset_done.html` — confirmation that email was sent
- `password_reset_confirm.html` — new password form
- `password_reset_complete.html` — success confirmation

---

## Email Notifications

Triggered from `admin_panel` view on user approval/rejection:

- Approval email: subject "Your NUC Legal AI account has been approved", includes login URL and role
- Rejection email: subject "NUC Legal AI — Account status update", advises contacting admin
- Both use `fail_silently=True` — email failure never breaks the admin action
- Email backend configurable: defaults to console backend locally, SMTP in production

---

## Session Management

- Engine: `django.contrib.sessions.backends.db` (database-backed)
- Cookie age: 3600 seconds (1 hour)
- `case_context` key: stores case data after analysis for chatbot use (summary, input_text, appellant, category, outcome, sections, prediction, confidence, similar_cases)
- `chat_session_id` key: stores the active `ChatSession` PK for message persistence

---

## Static File Handling

- `STATICFILES_STORAGE`: `whitenoise.storage.CompressedManifestStaticFilesStorage` — serves compressed, cache-busted static files in production
- `STATIC_ROOT`: `legal_ai_project/staticfiles/` — collected by `collectstatic`
- `STATICFILES_DIRS`: `legal_ai_project/static/` — source directory
- WhiteNoise middleware sits directly after `SecurityMiddleware` for efficient static serving without a separate web server

---

## Application Name

The app is branded as "Nyaya Sahayak" in all user-facing templates (nav, page titles, landing page). The internal project name is "NUC Legal AI" used in code, logs, and email communications.

---

## Verdict Signal Stripping (Data Leakage Prevention)

**File**: `app/extractor.py` — `strip_verdict_signals(text)`

The original `build_input_text` included verdict sentences ("the appeal is hereby allowed", "stand disposed of accordingly") in `input_text`. This caused data leakage — the model read the answer directly from the text rather than learning from legal reasoning.

`strip_verdict_signals()` removes any sentence matching 23 verdict patterns before the text is used for training or inference:

- Direct outcome statements: "appeal is hereby allowed/dismissed", "we allow/dismiss", "stand disposed of"
- Conviction outcomes: "conviction set aside", "acquitted", "hereby quashed"
- Sentence modifications: "sentence reduced/modified/commuted"
- Remand: "remanded back/to"
- Impugned order outcomes: "impugned order set aside/upheld/confirmed"
- Result markers: "in the result, the appeal", "in view of the above, the appeal", "for the above reasons"
- Pending applications boilerplate: "pending application(s), if any"

Applied in two places:
1. `build_input_text()` — strips before building the training text
2. `views.py` `analyze_case` — strips at inference time before calling `predict()`

The existing `processed.csv` was also retroactively cleaned by running the stripper over all 426 rows. After stripping: zero hard leakage (no "hereby allowed/dismissed" or "we allow/dismiss" remaining).

---

## ML Classifier — Upgrade Details

**File**: `app/ml/classifier.py`

### Architecture

Replaced plain `LogisticRegression` with a `VotingClassifier` ensemble:

```
VotingClassifier (soft voting, weights=[2,1])
├── Pipeline: StandardScaler → CalibratedClassifierCV(LinearSVC, isotonic, cv=3)
└── Pipeline: StandardScaler → LogisticRegression(lbfgs, balanced)
```

- `CalibratedClassifierCV` with isotonic regression gives properly calibrated probabilities
- Soft voting: ensemble averages `predict_proba` from both models, SVM weighted 2x
- `class_weight="balanced"` on both models handles 79:21 class imbalance

### Training

5-fold stratified cross-validation runs during every `build_ml`:
- Prints per-fold scores and mean ± std
- Saves results to `data/model_meta.json`
- Final model trained on all data after CV

### Decision Threshold

`predict()` uses `P(Allowed) >= 0.62` instead of the default 0.5:
- Compensates for 79:21 class imbalance (model is biased toward predicting Allowed)
- Reduces false "Favorable" predictions on ambiguous/disposed cases
- Confidence clamped to `[0.50, 0.99]`

### Results

| Metric | Value |
|---|---|
| CV Accuracy | 93.4% ± 2.6% |
| Per-fold scores | [97.5, 92.4, 92.4, 94.9, 89.7] |
| Training samples | 394 (after verdict stripping) |
| Class distribution | 90 Dismissed, 304 Allowed |

---

## Similarity Search — Upgrade Details

**File**: `app/ml/similarity.py`, `app/ml/embeddings.py`

### Rich Metadata

`build_ml` now saves `data/similarity_meta.json` alongside embeddings. Each entry contains:
- `case_id` — INSC citation
- `outcome` — Allowed / Dismissed / Disposed etc.
- `category` — Criminal / Civil / Tax etc.
- `sections` — cited legal sections

`find_similar()` returns enriched dicts with all these fields. The result page displays outcome badges (green for Allowed, red for Dismissed) and category tags on each similar case.

### `save_dataset_embeddings` signature change

```python
save_dataset_embeddings(texts: list[str], meta_records: list[dict] | None = None)
```

`build_ml.py` passes `meta_records` extracted from `processed.csv` columns.

---

## AI Correction — Upgrade Details

**File**: `app/correction.py`

### Context window

Cohere now receives the first **4000 chars** of the judgment (up from 2000). This covers the judgment header, parties, and facts section — giving better summaries and more accurate field corrections.

### Summary prompt

Upgraded from "4-6 sentence summary" to a structured 5-7 sentence prompt covering:
1. Case type and parties
2. Core legal dispute
3. Key sections/laws involved
4. What the lower court decided
5. What the Supreme Court decided and why
6. Practical significance

### `detect_issues()` — expanded checks

Now catches 3 additional error patterns:
- Sections without any known act name (raw numbers only)
- UUID/hash prefix in appellant name
- "Other" category on a long document (usually misclassified)
- "Unknown" outcome on a long document

---

## Dataset Management — Upgrade Details

**File**: `app/utils.py`

### Deduplication

`save_to_dataset()` checks `case_id` against `processed.json` before writing. If a case with the same `case_id` already exists, the record is silently skipped. Prevents the same judgment from inflating the dataset when analyzed multiple times.

### Column consistency

All 6 columns (`case_id`, `input_text`, `label`, `category`, `outcome`, `sections`) are always written to both CSV and JSON, even if some fields are empty strings.

---

## Chatbot — Upgrade Details

**File**: `app/chatbot/chatbot.py`, `app/views.py`

### Conversation memory

`chatbot_api` view now loads the last 8 messages (4 exchanges) from the `ChatSession` DB record and passes them as `history` to `generate_chat_response()`. These are forwarded to OCI as `chat_history` in the `CohereChatRequest`. The chatbot remembers what it said in the current session.

### `generate_chat_response` signature

```python
def generate_chat_response(
    user_query: str,
    context: dict,
    action: str = "",
    mode: str = "case",
    history: list | None = None,
) -> str
```

`history` is a list of `{"role": "user"|"assistant", "content": "..."}` dicts.

### Token and temperature changes

| Parameter | Before | After |
|---|---|---|
| `max_tokens` | 300 | 500 |
| `temperature` | 0.2 | 0.3 |

### Prompt context

`_case_block()` in `prompts.py` now:
- Uses AI summary as primary context (not rule-based `input_text`)
- Includes outcome and category tags on similar cases: `[73.2% match] [Allowed](Criminal) ...`

---

## UX Enhancements

### Result page

- Verdict hero: entrance animation (scale+fade, 120ms delay)
- Confidence ring: SVG circle with animated `stroke-dashoffset` fill
- Case Narrative block: structured Facts → Legal Context → Outcome derived from extracted fields (no AI call)
- Risk Assessment block: rule-based meter (confidence + outcome + section count → Low/Medium/High)
- Similar cases: outcome badges (green/red), category tags, INSC citation, sections in modal
- ML Insights: CV accuracy badge ("92% ± 3%"), training sample count
- Share button: copies formatted summary to clipboard (Ctrl+Shift+S)
- PDF export: `window.print()` with full print stylesheet — hides chatbot/nav, renders clean black-on-white layout with "Nyaya Sahayak" header
- Copy button on AI summary
- Keyboard shortcuts: Ctrl+Shift+S (share), Ctrl+Shift+P (print), Escape (close modals)

### Dashboard

- Animated number counters: stats count up from 0 with ease-out cubic on page load
- Category distribution: top 4 categories with animated CSS bar charts
- AI Stack status panel: live status of InLegalBERT, Cohere, OCI, Similarity Search
- CTA hero for new users with zero activity
- Recent sessions increased from 5 to 6

### Chatbot

- Typewriter effect: AI responses type out character by character at 10ms/char
- Markdown rendering: `**bold**`, `*italic*`, `` `code` ``, bullet lists, numbered lists rendered as HTML
- Quick action buttons: 3×2 grid layout with icons (more prominent, feels central)
- Chatbot panel header: gradient background with pulsing online indicator

### Mobile responsiveness

- Result page: collapses to single column below 860px, insight cards to 2-col below 860px, 1-col below 540px
- Chat page: nav links hidden, padding reduced, quick action buttons smaller below 600px
- Nav: links hidden below 600px

### Print stylesheet

`@media print` in `result_enhanced.css`:
- Hides nav, chatbot panel, buttons, modals
- Renders all blocks with black text on white background
- Adds "Nyaya Sahayak — AI Legal Analysis Report" header
- Prevents page breaks inside blocks

### Template filter

`app/templatetags/app_filters.py` — `split_csv` filter for splitting comma-separated strings in templates. Registered but not currently used (replaced by passing `sections_list` pre-split from the view).

### `sections_list` context variable

`analyze_case` view pre-splits `result["sections"]` into a Python list and passes it as `sections_list` to `result.html`. All three section pill loops use `sections_list` directly — avoids Django template `.split()` limitation.

### `model_meta` context variable

`analyze_case` view loads `data/model_meta.json` via `load_meta()` and passes it as `model_meta` to `result.html`. Used to display CV accuracy and training sample count in the ML Insights block.

---

## `outcome_display_from_text` Utility

**File**: `app/utils.py`

Maps any raw outcome string from the extractor to a human-readable display label:

| Outcome | Display |
|---|---|
| Allowed | Favorable (Appeal Allowed) |
| Dismissed | Unfavorable (Appeal Dismissed) |
| Acquitted | Favorable (Acquitted) |
| Quashed | Favorable (Quashed) |
| Partly Allowed | Partially Favorable (Partly Allowed) |
| Disposed | Disposed of |
| Remanded | Remanded for Fresh Hearing |
| Directions Issued | Directions Issued |
| Sentence Reduced/Modified | Partially Favorable (Sentence Modified) |

Used when the ML prediction is available but the extracted outcome provides additional nuance.

"""
Indian Supreme Court Judgment PDF Extractor
Extracts structured fields from all PDFs in the 2025/ folder.

Text extraction pipeline (in priority order):
  1. pdfminer.six  — best layout-aware text reconstruction for these PDFs
  2. pdfplumber    — fallback with its own extraction
Output: judgments_extracted.csv + judgments_extracted.json
"""

import re
import csv
import json
from pathlib import Path
from tqdm import tqdm
import pdfplumber

# pdfminer for cleaner text extraction
from pdfminer.high_level import extract_text as pdfminer_extract
from pdfminer.layout import LAParams

PDF_DIR = Path("2025")
OUTPUT_CSV = "judgments_extracted.csv"
OUTPUT_JSON = "judgments_extracted.json"

# ── Outcome keyword maps ──────────────────────────────────────────────────────
OUTCOME_PATTERNS = [
    # ── Partly allowed (check before plain allowed) ───────────────────────────
    (r"\bpartly\s+allowed\b", "Partly Allowed"),
    (r"\bpartially\s+allowed\b", "Partly Allowed"),
    (r"\ballow(?:ed|s)?\s+in\s+part\b", "Partly Allowed"),

    # ── Allowed ───────────────────────────────────────────────────────────────
    (r"\bappeal[s]?\s+(?:is\s+|are\s+)?(?:hereby\s+)?allowed\b", "Allowed"),
    (r"\bwe\s+allow\s+the\s+appeal[s]?\b", "Allowed"),
    (r"\bwe\s+allow\s+(?:this|these|both)\s+appeal[s]?\b", "Allowed"),
    (r"\baccordingly[,\s]+(?:we\s+)?allow\s+the\s+appeal[s]?\b", "Allowed"),
    (r"\bpetition[s]?\s+(?:is|are)\s+(?:hereby\s+)?allowed\b", "Allowed"),
    (r"\bwrit\s+petition[s]?\s+(?:is|are)\s+(?:hereby\s+)?allowed\b", "Allowed"),
    (r"\bwe\s+allow\s+the\s+(?:writ\s+)?petition[s]?\b", "Allowed"),
    (r"\bimpugned\s+(?:judgment|order|decision)\s+(?:is\s+)?(?:hereby\s+)?set\s+aside\b", "Allowed"),
    (r"\bimpugned\s+(?:judgment|order)\s+(?:are\s+)?set\s+aside\b", "Allowed"),

    # ── Dismissed ─────────────────────────────────────────────────────────────
    (r"\bappeal[s]?\s+(?:is\s+|are\s+)?(?:hereby\s+)?dismissed\b", "Dismissed"),
    (r"\bwe\s+dismiss\s+the\s+appeal[s]?\b", "Dismissed"),
    (r"\baccordingly[,\s]+(?:we\s+)?dismiss\s+the\s+appeal[s]?\b", "Dismissed"),
    (r"\bpetition[s]?\s+(?:is|are)\s+(?:hereby\s+)?dismissed\b", "Dismissed"),
    (r"\bwrit\s+petition[s]?\s+(?:is|are)\s+(?:hereby\s+)?dismissed\b", "Dismissed"),
    (r"\bwe\s+dismiss\s+the\s+(?:writ\s+)?petition[s]?\b", "Dismissed"),
    (r"\blacks?\s+merit[s]?\s+and\s+(?:is\s+|are\s+)?(?:hereby\s+)?dismissed\b", "Dismissed"),

    # ── Disposed ──────────────────────────────────────────────────────────────
    (r"\bstand[s]?\s+disposed\s+of\b", "Disposed"),
    (r"\bstand[s]?\s+disposed\b", "Disposed"),
    (r"\bappeal[s]?\s+stand[s]?\s+disposed\b", "Disposed"),
    (r"\bdisposed\s+of\s+accordingly\b", "Disposed"),

    # ── Acquitted / Set aside conviction ─────────────────────────────────────
    (r"\bconviction\s+and\s+sentence\s+(?:of\s+the\s+appellant[s]?\s+)?(?:are|is)\s+(?:accordingly\s+)?set\s+aside\b", "Acquitted"),
    (r"\bconviction\s+(?:is\s+)?(?:hereby\s+|accordingly\s+)?set\s+aside\b", "Acquitted"),
    (r"\bacquitted\b", "Acquitted"),
    (r"\bentitled\s+to\s+(?:the\s+)?benefit\s+of\s+doubt\b", "Acquitted"),

    # ── Quashed ───────────────────────────────────────────────────────────────
    (r"\bhereby\s+quashed\b", "Quashed"),
    (r"\bquashed\s+and\s+set\s+aside\b", "Quashed"),

    # ── Sentence modified ─────────────────────────────────────────────────────
    (r"\bsentence\s+(?:is\s+)?(?:hereby\s+|accordingly\s+)?reduced\b", "Sentence Reduced"),
    (r"\bsentence\s+(?:is\s+)?(?:hereby\s+|accordingly\s+)?modified\b", "Sentence Modified"),
    (r"\bsentence\s+(?:is\s+)?commuted\b", "Sentence Modified"),

    # ── Remanded ──────────────────────────────────────────────────────────────
    (r"\bremanded\s+back\b", "Remanded"),
    (r"\bremanded\s+to\s+the\b", "Remanded"),
    (r"\bmatter\s+is\s+remanded\b", "Remanded"),

    # ── Directions / Interim ──────────────────────────────────────────────────
    (r"\bwe\s+(?:hereby\s+)?direct\b.*\blist(?:ed)?\s+(?:on|after|before)\b", "Directions Issued"),
    (r"\btreat\s+this\s+matter\s+as\s+part\s+heard\b", "Part Heard / Interim Order"),
    (r"\binterim\s+(?:order|relief|direction)\b", "Part Heard / Interim Order"),
    (r"\blist(?:ed)?\s+(?:on|after|before)\b.*\bfurther\s+directions?\b", "Directions Issued"),
]

# ── Category keyword maps ─────────────────────────────────────────────────────
CATEGORY_PATTERNS = [
    (r"\bcriminal\s+appeal\b", "Criminal"),
    (r"\bcriminal\s+appellate\b", "Criminal"),
    (r"\bsessions\s+case\b", "Criminal"),
    (r"\bwrit\s+petition\s+\(criminal\)\b", "Criminal - Writ"),
    (r"\bnarcotics?\b", "Criminal - NDPS"),
    (r"\bndps\b", "Criminal - NDPS"),
    (r"\bmurder\b|\bsection\s+302\b", "Criminal - Murder"),
    (r"\brape\b|\bsection\s+376\b", "Criminal - Sexual Offence"),
    (r"\bcivil\s+appeal\b", "Civil"),
    (r"\bcivil\s+appellate\b", "Civil"),
    (r"\bconsumer\s+protection\b", "Civil - Consumer"),
    (r"\barbitration\b", "Civil - Arbitration"),
    (r"\binsolvency\b|\bibc\b", "Civil - Insolvency"),
    (r"\bmotor\s+accident\b|\bmact\b", "Civil - Motor Accident"),
    (r"\bservice\s+matter\b|\bservice\s+law\b", "Service Law"),
    (r"\btax\b|\bincome.tax\b|\bexcise\b|\bgst\b|\bcustoms\b", "Tax"),
    (r"\bwrit\s+petition\b", "Constitutional / Writ"),
    (r"\bconstitution\b|\bfundamental\s+right\b", "Constitutional / Writ"),
    (r"\bproperty\b|\btitle\s+suit\b|\bpossession\b", "Civil - Property"),
    (r"\bmatrimonial\b|\bdivorce\b|\bcustody\b", "Family Law"),
    (r"\blabour\b|\bworkmen\b|\bindustrial\s+dispute\b", "Labour / Industrial"),
    (r"\belectoral\b|\belection\b", "Electoral"),
    (r"\benforcement\s+directorate\b|\bpmla\b|\bmoney\s+launder", "Criminal - PMLA"),
    (r"\bcbi\b|\bcorruption\b|\bprevention\s+of\s+corruption\b", "Criminal - Corruption"),
    (r"\btenancy\b|\brent\b|\beviction\b", "Civil - Tenancy"),
    (r"\binsurance\b", "Civil - Insurance"),
    (r"\bcompany\b|\bcorporate\b|\bsebi\b", "Corporate / Securities"),
    (r"\benvironment\b|\bpollution\b|\bforest\b", "Environmental"),
    (r"\bspecial\s+leave\s+petition\b|\bslp\b", "SLP"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def clean(text: str) -> str:
    """Collapse whitespace artifacts common in pdfplumber output."""
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
    print(len(text))


def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Extract full text using pdfminer.six (primary) with pdfplumber as fallback.
    pdfminer gives better layout reconstruction — it respects line breaks and
    paragraph flow, avoiding the wide-space artifacts pdfplumber produces on
    these Indian Kanoon PDFs.
    """
    text = ""

    # ── 1. pdfminer.six ───────────────────────────────────────────────────────
    try:
        laparams = LAParams(
            line_margin=0.5,      # tighter line grouping
            word_margin=0.1,      # tighter word spacing
            char_margin=2.0,      # chars within this distance = same word
            boxes_flow=0.5,       # balance horizontal vs vertical flow
            detect_vertical=False,
        )
        text = pdfminer_extract(str(pdf_path), laparams=laparams) or ""
        text = clean(text)
    except Exception as e:
        pass

    # ── 2. pdfplumber fallback ────────────────────────────────────────────────
    if not text.strip():
        try:
            pages = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text(x_tolerance=3, y_tolerance=3)
                    if t:
                        pages.append(t)
            text = clean("\n".join(pages))
        except Exception as e:
            print(f"[ERROR] {pdf_path.name}: {e}")

    return text


def parse_filename(filename: str) -> dict:
    """
    Filename pattern: Appellant_vs_Respondent_on_DD_Month_YYYY_1.PDF
    Returns appellant, respondent, judgment_date parsed from filename.
    """
    stem = Path(filename).stem  # strip .PDF
    stem = re.sub(r"_\d+$", "", stem)  # remove trailing _1

    # Split on '_vs_' (case-insensitive)
    vs_match = re.split(r"_vs_", stem, maxsplit=1, flags=re.IGNORECASE)
    if len(vs_match) == 2:
        appellant_raw = vs_match[0]
        rest = vs_match[1]
    else:
        appellant_raw = stem
        rest = ""

    # Extract date from end: _on_DD_Month_YYYY
    date_match = re.search(
        r"_on_(\d{1,2})_([A-Za-z]+)_(\d{4})$", rest, re.IGNORECASE
    )
    if date_match:
        day, month, year = date_match.groups()
        judgment_date = f"{day} {month} {year}"
        respondent_raw = rest[: date_match.start()]
    else:
        judgment_date = ""
        respondent_raw = rest

    appellant = appellant_raw.replace("_", " ").strip()
    respondent = respondent_raw.replace("_", " ").strip()
    return {
        "appellant": appellant,
        "respondent": respondent,
        "judgment_date": judgment_date,
    }


def extract_case_number(text: str) -> str:
    """
    Extract the primary case number from the header block.
    Handles patterns like:
      CRIMINAL APPEAL NO(S). 1122-1123 OF 2018
      CIVIL APPEAL NOS. 3994-3997 OF 2024
      CRIMINAL APPEAL NO.        OF 2025  (blank number — SLP converted)
      SPECIAL LEAVE PETITION (Crl.) NO. 1959 OF 2022
      CONTEMPT PETITION (C) NO. 735 OF 2019
      WRIT PETITION (C) NO. 16921 OF 2014
    Only looks in first 1500 chars (header block).
    """
    head = text[:1500]

    patterns = [
        # Full typed: CRIMINAL/CIVIL APPEAL NOS. 1234-5678 OF 2024
        r"((?:CRIMINAL|CIVIL)\s+APPEAL\s+NO[S]?\.?\s*[\d][\d\-/]*\s+OF\s+\d{4})",
        # With blank number (SLP converted): CRIMINAL APPEAL NO.   OF 2025
        r"((?:CRIMINAL|CIVIL)\s+APPEAL\s+NO[S]?\.?\s+OF\s+\d{4})",
        # WRIT PETITION
        r"(WRIT\s+PETITION\s+\([A-Z]+\)\s+NO[S]?\.?\s*[\d][\d\-/]*\s+OF\s+\d{4})",
        # SPECIAL LEAVE PETITION
        r"(SPECIAL\s+LEAVE\s+PETITION\s+\([A-Z]+\.?\)\s+NO[S]?\.?\s*[\d][\d\-/]*\s+OF\s+\d{4})",
        # SLP short form
        r"(SLP\s+\([A-Z]+\.?\)\s+NO[S]?\.?\s*[\d][\d\-/]*\s+OF\s+\d{4})",
        # CONTEMPT PETITION
        r"(CONTEMPT\s+PETITION\s+\([A-Z]+\)\s+NO[S]?\.?\s*[\d][\d\-/]*\s+OF\s+\d{4})",
        # TRANSFER PETITION
        r"(TRANSFER\s+PETITION\s+\([A-Z]+\)\s+NO[S]?\.?\s*[\d][\d\-/]*\s+OF\s+\d{4})",
        # Generic fallback: anything with NO. NNN OF YYYY
        r"((?:CRIMINAL|CIVIL|WRIT|SPECIAL|CONTEMPT|TRANSFER|REVIEW|CURATIVE)"
        r"[\w\s\(\)\.]+?NO[S]?\.?\s*[\d][\d\-/]*\s+OF\s+\d{4})",
    ]
    for pat in patterns:
        m = re.search(pat, head, re.IGNORECASE)
        if m:
            val = re.sub(r"\s+", " ", m.group(1)).strip()
            # Skip if it's just "NO. OF 2025" with no number
            if re.search(r"\d{3,}", val):
                return val
    return ""


def extract_case_id(text: str) -> str:
    """
    Extract INSC citation e.g. '2025 INSC 35'.
    - Only picks the FIRST occurrence (= current case header, not cited cases)
    - Handles spaced-out characters like '2 0 2 5  I N S C  3 5'
    """
    # Fix spaced-out letters in INSC only (e.g. "I N S C" → "INSC")
    normalized = re.sub(r"\bI\s+N\s+S\s+C\b", "INSC", text)

    # Find ALL matches, return the first one
    matches = list(re.finditer(r"\b(20\d{2})\s+(INSC)\s+(\d+)\b", normalized, re.IGNORECASE))
    if matches:
        m = matches[0]
        return f"{m.group(1)} INSC {m.group(3)}"
    return ""


def extract_sections(text: str) -> str:
    """
    Extract statutory sections tied to a known act.
    Handles: 'Section 302 IPC', 'sub-section (1) of Section 37 FSS Act',
             'Section 2(y) of the RPwD Act', 'Section 198(4) of the UP ZA Act',
             'Section NNN thereof', 'Section NNN of the Act'
    Returns normalized format: "302 IPC, 138 NI Act"
    """
    ACTS = [
        (r"Indian\s+Penal\s+Code|(?<!\w)I\.?P\.?C\.?(?!\w)",                    "IPC"),
        (r"Bharatiya\s+Nyaya\s+Sanhita|(?<!\w)B\.?N\.?S\.?(?!\w)",              "BNS"),
        (r"Code\s+of\s+Criminal\s+Procedure|(?<!\w)Cr\.?P\.?C\.?(?!\w)",        "CrPC"),
        (r"Bharatiya\s+Nagarik\s+Suraksha\s+Sanhita|(?<!\w)B\.?N\.?S\.?S\.?(?!\w)", "BNSS"),
        (r"Code\s+of\s+Civil\s+Procedure|(?<!\w)C\.?P\.?C\.?(?!\w)",            "CPC"),
        (r"NDPS\s+Act|Narcotic\s+Drugs\s+and\s+Psychotropic",                   "NDPS Act"),
        (r"Prevention\s+of\s+Money.Laundering|(?<!\w)PMLA(?!\w)",               "PMLA"),
        (r"Prevention\s+of\s+Corruption\s+Act",                                  "PC Act"),
        (r"Information\s+Technology\s+Act",                                       "IT Act 2000"),
        (r"Income.Tax\s+Act|(?<!\w)I\.T\.\s+Act(?!\w)",                         "IT Act"),
        (r"Companies\s+Act",                                                      "Companies Act"),
        (r"Consumer\s+Protection\s+Act",                                          "Consumer Protection Act"),
        (r"Negotiable\s+Instruments\s+Act|(?<!\w)N\.I\.\s+Act(?!\w)",           "NI Act"),
        (r"(?<!\w)Evidence\s+Act(?!\w)",                                          "Evidence Act"),
        (r"Motor\s+Vehicles\s+Act",                                               "MV Act"),
        (r"Arbitration\s+and\s+Conciliation\s+Act|Arbitration\s+Act",           "Arbitration Act"),
        (r"Insolvency\s+and\s+Bankruptcy\s+Code|(?<!\w)IBC(?!\w)",              "IBC"),
        (r"(?<!\w)Customs\s+Act(?!\w)",                                           "Customs Act"),
        (r"Central\s+Excise\s+Act",                                               "Central Excise Act"),
        (r"Juvenile\s+Justice\s+Act|(?<!\w)J\.J\.\s+Act(?!\w)",                 "JJ Act"),
        (r"Protection\s+of\s+Children\s+from\s+Sexual|(?<!\w)POCSO(?!\w)",      "POCSO"),
        (r"Specific\s+Relief\s+Act",                                              "Specific Relief Act"),
        (r"Transfer\s+of\s+Property\s+Act",                                       "TP Act"),
        (r"Hindu\s+Marriage\s+Act",                                               "Hindu Marriage Act"),
        (r"Hindu\s+Succession\s+Act",                                             "Hindu Succession Act"),
        (r"Forest\s+Conservation\s+Act",                                          "Forest Conservation Act"),
        (r"Wild\s+Life\s+\(?Protection\s+\)?Act|Wildlife\s+\(?Protection\s+\)?Act", "Wildlife Act"),
        (r"Factories\s+Act",                                                      "Factories Act"),
        (r"Representation\s+of\s+the\s+People\s+Act",                           "RP Act"),
        (r"(?<!\w)GST\s+Act|Goods\s+and\s+Services\s+Tax",                      "GST Act"),
        (r"SARFAESI\s+Act|Securitisation\s+and\s+Reconstruction",               "SARFAESI Act"),
        (r"Real\s+Estate\s+(?:Regulatory\s+)?(?:Authority|Act)|(?<!\w)RERA(?!\w)", "RERA"),
        (r"Rights\s+of\s+Persons\s+with\s+Disabilities|(?<!\w)RPwD\s+Act|RPWD\s+Act(?!\w)", "RPwD Act"),
        (r"Food\s+Safety\s+and\s+Standards\s+Act|(?<!\w)FSS\s+Act(?!\w)",       "FSS Act"),
        (r"Arms\s+Act",                                                           "Arms Act"),
        (r"Contempt\s+of\s+Courts\s+Act",                                        "Contempt Act"),
        (r"Land\s+Acquisition\s+Act",                                             "Land Acquisition Act"),
        (r"U\.?P\.?\s+Zamindari\s+Abolition|Zamindari\s+Abolition",             "UP ZA Act"),
        (r"Service\s+Tax",                                                        "Service Tax"),
        (r"Constitution\s+of\s+India",                                            "Constitution"),
        (r"Kerala\s+Police\s+Act",                                                "Kerala Police Act"),
        (r"Tamil\s+Nadu\s+Prohibition\s+of\s+Harassment\s+of\s+Women\s+Act|Tamil\s+Nadu\s+Harassment\s+of\s+Women\s+Act", "TN Harassment of Women Act"),
    ]

    # Handles: 302, 12A, 2(y), 37(1), 141(2)(a), 198(4)
    SEC_NUM = r"\d{1,4}(?:[A-Z]|\(\w+\))*"

    results = []
    seen = set()

    def add(num: str, label: str):
        key = f"{num} {label}"
        if key not in seen:
            seen.add(key)
            results.append(key)

    # ── Pass 1: "Section(s) NNN [, NNN]* ... <act within 150 chars>" ─────────
    for act_pat, act_label in ACTS:
        pattern = (
            r"(?:sub-\s*)?[Ss]ections?\s+"
            r"((?:" + SEC_NUM + r")(?:\s*[,/]\s*(?:" + SEC_NUM + r"))*"
            r"(?:\s+(?:and|&)\s+(?:" + SEC_NUM + r"))*)"
            r"(?:[^.]{0,150}?)"
            r"(?:" + act_pat + r")"
        )
        for m in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
            for num in re.findall(SEC_NUM, m.group(1)):
                add(num, act_label)

    # ── Pass 2: "Section NNN of the <ActName>" directly ──────────────────────
    for act_pat, act_label in ACTS:
        direct = (
            r"(?:sub-\s*)?[Ss]ection\s+(" + SEC_NUM + r")"
            r"\s+of\s+(?:the\s+)?"
            r"(?:" + act_pat + r")"
        )
        for m in re.finditer(direct, text, re.IGNORECASE):
            add(m.group(1), act_label)

    # ── Pass 3: inline short forms — "u/s 302 IPC", "under Section 302 IPC" ──
    for act_pat, act_label in ACTS:
        short = (
            r"(?:u/s|under\s+[Ss]ection)\s+(" + SEC_NUM + r")"
            r"(?:\s+(?:and|&|,)\s+(?:" + SEC_NUM + r"))*"
            r"\s+(?:" + act_pat + r")"
        )
        for m in re.finditer(short, text, re.IGNORECASE):
            add(m.group(1), act_label)

    # ── Pass 4: "Section NNN thereof/of the Act" — resolve from ±500 chars ───
    for m in re.finditer(
        r"(?:sub-\s*)?[Ss]ection\s+(" + SEC_NUM + r")"
        r"\s+(?:thereof|of\s+(?:the\s+)?(?:said\s+)?[Aa]ct)",
        text
    ):
        num = m.group(1)
        ctx = text[max(0, m.start()-500): min(len(text), m.end()+500)]
        for act_pat, act_label in ACTS:
            if re.search(act_pat, ctx, re.IGNORECASE):
                add(num, act_label)
                break

    return ", ".join(results[:25]) if results else ""



def extract_outcome(text: str) -> str:
    """Scan last ~4000 chars for outcome keywords, in priority order."""
    tail = text[-4000:]
    for pattern, label in OUTCOME_PATTERNS:
        if re.search(pattern, tail, re.IGNORECASE | re.DOTALL):
            return label
    # Broad fallbacks — only if nothing matched above
    if re.search(r"\bwe\s+allow\b|\ballowed\b", tail, re.IGNORECASE):
        return "Allowed"
    if re.search(r"\bwe\s+dismiss\b|\bdismissed\b", tail, re.IGNORECASE):
        return "Dismissed"
    if re.search(r"\bdisposed\b", tail, re.IGNORECASE):
        return "Disposed"
    if re.search(r"\bdirections?\s+issued\b|\bwe\s+(?:hereby\s+)?direct\b", tail, re.IGNORECASE):
        return "Directions Issued"
    return "Unknown"


def classify_category(text: str) -> str:
    """Classify judgment category from first ~2000 chars."""
    head = text[:2000].lower()
    for pattern, label in CATEGORY_PATTERNS:
        if re.search(pattern, head, re.IGNORECASE):
            return label
    return "Other"


def extract_judgment_date_from_text(text: str, fallback: str) -> str:
    """
    Extract the pronouncement date from the signature block.
    Prioritises the date that immediately follows 'NEW DELHI' in the last ~1000 chars,
    which is the actual pronouncement date (not a future listing date).
    """
    MONTH = (
        r"(?:January|February|March|April|May|June|July|"
        r"August|September|October|November|December)"
    )
    DATE_PAT = rf"\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTH}[,\s]+\d{{4}}"

    tail = text[-1000:]

    # 1. Date right after "NEW DELHI" / "New Delhi" (pronouncement date)
    m = re.search(
        rf"(?:New\s+Delhi|NEW\s+DELHI)[;,.\s]+\n?\s*({DATE_PAT})",
        tail,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    # 2. Month-name date on its own line near the very end (last 300 chars)
    for m in re.finditer(rf"({DATE_PAT})", tail[-300:], re.IGNORECASE):
        return m.group(1).strip()

    return fallback


# ── Label mapping ─────────────────────────────────────────────────────────────
FAVORABLE_OUTCOMES = {"Allowed", "Acquitted", "Quashed", "Sentence Reduced", "Sentence Modified"}

def get_label(outcome: str) -> int | None:
    """
    Final rule for ML training labels:
      1 = Allowed
      0 = Dismissed
      None = Disposed, Partly allowed, Unknown, etc. (removed)
    """
    if not outcome: return None
    outcome = outcome.lower()

    if "partly allowed" in outcome or "partially allowed" in outcome:
        return None
    elif "allowed" in outcome:
        return 1
    elif "dismissed" in outcome:
        return 0
    else:
        return None   # remove these rows


def _clean_body(text: str) -> str:
    """
    Deep-clean a judgment body. Removes all noise while preserving legal prose.
    """
    t = text

    # ── 1. Binary / encoding artifacts ───────────────────────────────────────
    t = re.sub(r"\x0c", "\n", t)                          # form feeds
    t = re.sub(r"\(cid:\d+\)", "", t)                     # (cid:131) currency symbols
    t = re.sub(r"\\u[0-9a-fA-F]{4}", "", t)               # unicode escapes

    # ── 2. URLs and external references ──────────────────────────────────────
    t = re.sub(r"Indian Kanoon\s*-\s*https?://\S+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"https?://\S+", "", t)

    # ── 3. Digital signature blocks ───────────────────────────────────────────
    t = re.sub(r"Date:\s*\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2}\s+IST\s*\n?\s*Reason:", "", t)
    t = re.sub(r"\bReason:\s*\n", "", t)   # leftover "Reason:" on its own
    t = re.sub(r"Digitally\s+signed\s+by\s+\S+.*?\n", "", t, flags=re.IGNORECASE)
    t = re.sub(r"Signature\s+Not\s+Verified.*?\n", "", t, flags=re.IGNORECASE)

    # ── 4. Spaced-out judge signatures in footer ──────────────────────────────
    # e.g. "… … … J . ( B . R . G A V A I ) … … … J . ( K . V . V I S W A N A T H A N )"
    t = re.sub(r"[…\.\s]{6,}J\s*\.\s*[\(\[].{3,40}[\)\]]", "", t)
    t = re.sub(r"(?:[A-Z]\s+\.?\s+){4,}[A-Z]", "", t)    # spaced caps: B . R . G A V A I

    # ── 5. Lone page numbers ──────────────────────────────────────────────────
    t = re.sub(r"^\s*\d{1,3}\s*$", "", t, flags=re.MULTILINE)

    # ── 6. Section/chapter headings that add no value ─────────────────────────
    HEADINGS = (
        r"JUDGMENT|J\s*U\s*D\s*G\s*M\s*E\s*N\s*T"
        r"|O\s*R\s*D\s*E\s*R"
        r"|REPORTABLE|NON.REPORTABLE"
        r"|IN THE SUPREME COURT OF INDIA"
        r"|BACKGROUND|BRIEF\s+RESUME\s+OF\s+FACTS|BRIEF\s+FACTS"
        r"|THE\s+APPEAL|THE\s+QUESTION|THE\s+ISSUE"
        r"|CONCLUSION|FINDINGS|ANALYSIS|DISCUSSION"
        r"|SUBMISSIONS?|ARGUMENTS?"
        r"|INDEX|FACTUAL\s+(?:MATRIX|BACKGROUND|DETAILS?)"
        r"|ISSUES?\s+FOR\s+CONSIDERATION"
    )
    t = re.sub(rf"^\s*(?:{HEADINGS})\s*$", "", t, flags=re.MULTILINE | re.IGNORECASE)

    # ── 7. Judge name lines ───────────────────────────────────────────────────
    # "DIPANKAR DATTA, J." / "J.K. MAHESHWARI, J." / "Mehta, J." / "VIKRAM NATH, J.:"
    t = re.sub(r"^[A-Z][A-Za-z\s\.\,]+,\s*J\.\s*:?\s*$", "", t, flags=re.MULTILINE)
    # "SATISH CHANDRA SHARMA, J." all caps
    t = re.sub(r"^[A-Z][A-Z\s\.]+,\s*J\.\s*$", "", t, flags=re.MULTILINE)

    # ── 8. Paragraph numbering at line start ──────────────────────────────────
    t = re.sub(r"^\s*\d{1,3}\.\s+", "", t, flags=re.MULTILINE)

    # ── 9. Footnote superscripts glued to words ───────────────────────────────
    # "Singh1" → "Singh", "20231" → "2023", "19735" → "1973"
    # Pattern: word char followed by 1-2 digits at word boundary before space/punct
    t = re.sub(r"(\b\w+?)(\d{1,2})(?=[\s,\.\;\:\)\]])", lambda m:
        m.group(1) if not m.group(1)[-1].isdigit() else m.group(0), t)
    # Specifically fix years with trailing footnote digit: "2024 2" or "20242"
    t = re.sub(r"\b((?:19|20)\d{2})\d{1,2}\b", r"\1", t)

    # ── 10. Case title repetition (page headers) ──────────────────────────────
    t = re.sub(
        r"^.{5,60}\s+vs\.?\s+.{5,60}\s+on\s+\d{1,2}\s+\w+,?\s+\d{4}\s*$",
        "", t, flags=re.MULTILINE | re.IGNORECASE
    )

    # ── 11. Author/Bench metadata ─────────────────────────────────────────────
    t = re.sub(r"^(?:Author|Bench)\s*:.*$", "", t, flags=re.MULTILINE | re.IGNORECASE)

    # ── 12. Bullet points / list markers ─────────────────────────────────────
    t = re.sub(r"^[\•\-\*]\s+", "", t, flags=re.MULTILINE)

    # ── 13. Whitespace normalisation ──────────────────────────────────────────
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t)

    return t.strip()


def _good_sentence(s: str) -> bool:
    """
    Return True if sentence is clean and meaningful.
    Rejects: too short, all-caps headers, broken fragments, OCR noise,
             sentences starting with bare numbers/case refs.
    """
    s = s.strip()
    if len(s) < 40:
        return False
    # All-caps header (e.g. "BACKGROUND", "THE APPEAL")
    if re.match(r"^[A-Z\s\.\-]{4,}$", s):
        return False
    # Starts with a bare case number or SLP ref: "4036-4038 of 2024..."
    if re.match(r"^\d[\d\-/]+\s+of\s+\d{4}", s, re.IGNORECASE):
        return False
    # Starts with a lone initial or number fragment
    if re.match(r"^[A-Z]\.\s", s):
        return False
    # Contains leftover "Reason:" artifact
    if re.search(r"\bReason:\s*$", s):
        return False
    # Contains broken year like "dated 7th March, 20" (year cut off < 4 digits)
    if re.search(r"\b(19|20)\d{0,1}\b(?!\d)", s):
        return False
    # Sentence is mostly numbers/symbols
    alpha = sum(c.isalpha() for c in s)
    if alpha / max(len(s), 1) < 0.5:
        return False
    return True


def extract_case_text(text: str) -> str:
    """
    Extract and deep-clean the judgment body.
    Returns clean prose with no headers, judge names, numbering, or noise.
    """
    m = re.search(r"\b(?:JUDGMENT|J\s*U\s*D\s*G\s*M\s*E\s*N\s*T|O\s*R\s*D\s*E\s*R)\b",
                  text, re.IGNORECASE)
    body = text[m.start():] if m else text

    # Cut at signature block
    sig = re.search(r"\n[…\.\s]{8,}(?:J\.|NEW DELHI|New Delhi)", body, re.IGNORECASE)
    if sig:
        body = body[:sig.start()]

    return _clean_body(body)


def _extract_decision_sentences(clean_body: str) -> list[str]:
    """
    Extract the final 1-2 sentences that contain the outcome signal.
    Operates on the already-cleaned body (no noise, no page headers).
    """
    OUTCOME_SIGNALS = (
        r"\baccordingly\b"
        r"|\bappeal[s]?\s+(?:is\s+|are\s+)?(?:hereby\s+)?(?:allowed|dismissed|disposed)"
        r"|\bpetition[s]?\s+(?:is\s+|are\s+)?(?:hereby\s+)?(?:allowed|dismissed|disposed)"
        r"|\bstand[s]?\s+disposed"
        r"|\bhereby\s+(?:allowed|dismissed|quashed|set\s+aside)"
        r"|\bset\s+aside\b"
        r"|\bconviction\s+.{0,40}set\s+aside"
        r"|\bacquitted\b"
        r"|\bappeal[s]?\s+lack[s]?\s+merit"
        r"|\bno\s+merit\b"
        r"|\bimpugned\s+(?:judgment|order)\s+.{0,30}(?:set\s+aside|upheld|confirmed)"
        r"|\bstand[s]?\s+restored"
        r"|\bremanded\b"
        r"|\bwe\s+allow\b|\bwe\s+dismiss\b"
    )
    # Work only from the last 2000 chars of the CLEAN body
    tail = clean_body[-2000:]
    # Flatten newlines so sentence splitting works correctly
    tail = re.sub(r"\n+", " ", tail)
    sentences = re.split(r"(?<=[.!?])\s+", tail)
    decision = []
    for s in sentences:
        s = s.strip()
        if _good_sentence(s) and re.search(OUTCOME_SIGNALS, s, re.IGNORECASE):
            decision.append(s)
    return decision[-2:] if decision else []


def build_input_text(text: str, sections: str, outcome: str, category: str) -> str:
    """
    Build clean, concise model-ready input_text (150-300 words):
      - 2 facts sentences (beginning)
      - 1-2 reasoning sentences (middle)
      - 1-2 decision sentences with explicit outcome signal (end)
      - Sections appended
    Single flat paragraph — no newlines, no noise.
    """
    m = re.search(r"\b(?:JUDGMENT|J\s*U\s*D\s*G\s*M\s*E\s*N\s*T|O\s*R\s*D\s*E\s*R)\b",
                  text, re.IGNORECASE)
    body = text[m.start():] if m else text
    sig = re.search(r"\n[…\.\s]{8,}(?:J\.|NEW DELHI|New Delhi)", body, re.IGNORECASE)
    if sig:
        body = body[:sig.start()]

    body = _clean_body(body)

    # Flatten to single-line prose — eliminates all \n in output
    flat = re.sub(r"\n+", " ", body)
    flat = re.sub(r"\s{2,}", " ", flat).strip()

    # Split into clean sentences
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", flat)
                 if _good_sentence(s)]

    if not sentences:
        base = flat[:600]
        if sections:
            base += f" Sections: {sections}."
        return base.strip()

    n = len(sentences)

    # ── Facts: first 2 good sentences ────────────────────────────────────────
    facts = sentences[:2]

    # ── Reasoning: 1-2 sentences from 40-70% of document ────────────────────
    mid_start = max(2, int(n * 0.40))
    mid_end   = max(mid_start + 2, int(n * 0.70))
    reasoning_pool = sentences[mid_start:mid_end]
    REASONING_SIGNALS = (
        r"\bcourt\b|\bheld\b|\bobserved\b|\bfound\b|\bliability\b"
        r"|\bevidence\b|\bprinciple\b|\bcannot\b|\bmust\b|\brequired\b"
        r"|\bestablished\b|\bproved\b|\bshown\b|\bdemonstrated\b"
    )
    reasoning = [s for s in reasoning_pool
                 if re.search(REASONING_SIGNALS, s, re.IGNORECASE)][:2]
    if not reasoning:
        reasoning = reasoning_pool[:1]

    # ── Decision: from clean body, must have outcome signal ──────────────────
    decision = _extract_decision_sentences(body)
    if not decision:
        decision = [s for s in sentences[-3:] if _good_sentence(s)][-2:]

    # ── Compose, deduplicate, strip any residual newlines ────────────────────
    seen = set()
    parts = []
    for s in facts + reasoning + decision:
        s = re.sub(r"\s+", " ", s).strip()
        if s not in seen:
            seen.add(s)
            parts.append(s)

    result = " ".join(parts)

    # ── Trim to 300 words ─────────────────────────────────────────────────────
    words = result.split()
    if len(words) > 300:
        result = " ".join(words[:300]).rsplit(".", 1)[0] + "."

    # ── Append sections ───────────────────────────────────────────────────────
    if sections:
        result += f" Sections: {sections}."

    return result.strip()



def extract_fields(pdf_path: Path) -> dict:
    filename = pdf_path.name
    text = extract_text_from_pdf(pdf_path)

    # From filename
    fn_data = parse_filename(filename)

    # From text
    case_id      = extract_case_id(text)
    case_number  = extract_case_number(text)
    sections     = extract_sections(text)
    outcome      = extract_outcome(text)
    category     = classify_category(text)
    word_count   = len(text.split())
    judgment_date = extract_judgment_date_from_text(text, fn_data["judgment_date"])
    label        = get_label(outcome)
    case_text    = extract_case_text(text)

    # Normalize sections: "S.302 IPC; S.376 IPC" → "302 IPC, 376 IPC"
    sections_norm = ""
    if sections:
        parts = [re.sub(r"^S\.", "", s.strip()) for s in sections.split(";")]
        sections_norm = ", ".join(p.strip() for p in parts if p.strip())

    input_text   = build_input_text(text, sections_norm, outcome, category)

    # Refine appellant/respondent from text header (first 800 chars)
    appellant = fn_data["appellant"]
    respondent = fn_data["respondent"]
    header = text[:800]

    # Use greedy match on a single line — captures full name including "& ORS."
    # The [^\n]+ greedily takes the whole line, then backtracks to find \.{2,}
    app_match = re.search(
        r"^([A-Z][^\n]{2,119}?)\s*\.{2,}\s*APPELLANT",
        header, re.IGNORECASE | re.MULTILINE,
    )
    res_match = re.search(
        r"^([A-Z][^\n]{2,119}?)\s*\.{2,}\s*RESPONDENT[S]?",
        header, re.IGNORECASE | re.MULTILINE,
    )
    if app_match:
        val = app_match.group(1).strip()
        if "\n" not in val and len(val) < 120:
            appellant = val.title()
    if res_match:
        val = res_match.group(1).strip()
        if "\n" not in val and len(val) < 120:
            respondent = val.title()

    # Quality flag: mark low-quality extractions (< 150 words in body)
    quality_ok = len(case_text.split()) >= 150

    return {
        "case_id":       case_id,
        "case_number":   case_number,
        "appellant":     appellant,
        "respondent":    respondent,
        "judgment_date": judgment_date,
        "sections":      sections_norm,
        "category":      category,
        "outcome":       outcome,
        "label":         label,
        "word_count":    word_count,
        "quality_ok":    quality_ok,
        "case_text":     case_text,
        "input_text":    input_text,
        "filename":      filename,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    pdf_files = sorted(PDF_DIR.glob("*.PDF")) + sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {PDF_DIR}/")
        return

    print(f"Found {len(pdf_files)} PDFs. Extracting...")
    results = []

    for pdf_path in tqdm(pdf_files, unit="file"):
        record = extract_fields(pdf_path)
        results.append(record)

    total_raw = len(results)

    #  Filter using pandas as requested ──────────────────────────────────────
    import pandas as pd
    df = pd.DataFrame(results)

    # 1. Start with raw extracted rows
    total_raw = len(df)

    # 2. Filter Bad Rows
    df = df[df['label'].notnull()]
    df = df[df['quality_ok'] == True]

    # Convert label to integer now that nulls are removed
    df['label'] = df['label'].astype(int)

    # 3. Use ONLY input_text
    df_final = df[['input_text', 'label']].copy()

    print(f"\nFiltered: {total_raw} total → {len(df_final)} usable records")
    print(f"  Dropped:     {total_raw - len(df_final)} records (ambiguous label or low quality)")

    #  Write CSV ─────────────────────────────────────────────────────────────
    df_final.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")

    #  Write JSON ────────────────────────────────────────────────────────────
    df_final.to_json(OUTPUT_JSON, orient="records", indent=2, force_ascii=False)

    print(f"\nDone. {len(df_final)} records written.")
    print(f"  CSV  → {OUTPUT_CSV}")
    print(f"  JSON → {OUTPUT_JSON}")

    # ── Quick stats ───────────────────────────────────────────────────────────
    outcomes = {}
    categories = {}
    labels = {0: 0, 1: 0}
    low_quality = 0
    for r in results:
        outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
        categories[r["category"]] = categories.get(r["category"], 0) + 1
        if r["label"] is not None:
            labels[r["label"]] = labels.get(r["label"], 0) + 1
        if not r["quality_ok"]:
            low_quality += 1

    print("\nOutcome distribution:")
    for k, v in sorted(outcomes.items(), key=lambda x: -x[1]):
        print(f"  {k:<28} {v}")

    print("\nCategory distribution:")
    for k, v in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {k:<35} {v}")

    print(f"\nLabel distribution:  0 (unfavorable)={labels[0]}  1 (favorable)={labels[1]}")
    print(f"Low quality records (< 150 words): {low_quality}")


if __name__ == "__main__":
    main()

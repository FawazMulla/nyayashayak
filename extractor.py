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

    Strategy:
    1. For each known act, find all 'Section(s) NNN ... <act>' mentions
       where the act name appears within 120 chars after the section number.
    2. Also resolve short inline forms: 'Section 302 IPC', 'S.138 NI Act'
    3. Also resolve 'Section NNN thereof' / 'Section NNN of the Act' by
       looking at the nearest act name mentioned in the surrounding 400 chars.
    """
    ACTS = [
        (r"Indian\s+Penal\s+Code|(?<!\w)I\.?P\.?C\.?(?!\w)",           "IPC"),
        (r"Code\s+of\s+Criminal\s+Procedure|(?<!\w)Cr\.?P\.?C\.?(?!\w)","CrPC"),
        (r"Code\s+of\s+Civil\s+Procedure|(?<!\w)C\.?P\.?C\.?(?!\w)",   "CPC"),
        (r"NDPS\s+Act|Narcotic\s+Drugs\s+and\s+Psychotropic",           "NDPS Act"),
        (r"Prevention\s+of\s+Money.Laundering|(?<!\w)PMLA(?!\w)",       "PMLA"),
        (r"Prevention\s+of\s+Corruption\s+Act",                         "PC Act"),
        (r"Income.Tax\s+Act|(?<!\w)I\.T\.\s+Act(?!\w)",                 "IT Act"),
        (r"Companies\s+Act",                                             "Companies Act"),
        (r"Consumer\s+Protection\s+Act",                                 "Consumer Protection Act"),
        (r"Negotiable\s+Instruments\s+Act|(?<!\w)N\.I\.\s+Act(?!\w)",   "NI Act"),
        (r"(?<!\w)Evidence\s+Act(?!\w)",                                 "Evidence Act"),
        (r"Motor\s+Vehicles\s+Act",                                      "MV Act"),
        (r"Arbitration\s+and\s+Conciliation\s+Act|Arbitration\s+Act",   "Arbitration Act"),
        (r"Insolvency\s+and\s+Bankruptcy\s+Code|(?<!\w)IBC(?!\w)",      "IBC"),
        (r"(?<!\w)Customs\s+Act(?!\w)",                                  "Customs Act"),
        (r"Central\s+Excise\s+Act",                                      "Central Excise Act"),
        (r"Juvenile\s+Justice\s+Act|(?<!\w)J\.J\.\s+Act(?!\w)",         "JJ Act"),
        (r"Protection\s+of\s+Children\s+from\s+Sexual|(?<!\w)POCSO(?!\w)", "POCSO"),
        (r"Specific\s+Relief\s+Act",                                     "Specific Relief Act"),
        (r"Transfer\s+of\s+Property\s+Act",                              "TP Act"),
        (r"Hindu\s+Marriage\s+Act",                                      "Hindu Marriage Act"),
        (r"Hindu\s+Succession\s+Act",                                    "Hindu Succession Act"),
        (r"Forest\s+Conservation\s+Act",                                 "Forest Conservation Act"),
        (r"Wild\s+Life\s+\(?Protection\s+\)?Act|Wildlife\s+\(?Protection\s+\)?Act", "Wildlife Act"),
        (r"Factories\s+Act",                                             "Factories Act"),
        (r"Representation\s+of\s+the\s+People\s+Act",                   "RP Act"),
        (r"(?<!\w)GST\s+Act|Goods\s+and\s+Services\s+Tax",              "GST Act"),
        (r"Service\s+Tax",                                               "Service Tax"),
        (r"(?<!\w)SARFAESI\s+Act|Securitisation\s+and\s+Reconstruction","SARFAESI Act"),
        (r"Real\s+Estate\s+(?:Regulatory\s+)?(?:Authority|Act)|(?<!\w)RERA(?!\w)", "RERA"),
    ]

    SEC_NUM = r"\d{1,4}[A-Z]?"

    results = []
    seen = set()

    def add(num: str, label: str):
        key = f"S.{num} {label}"
        if key not in seen:
            seen.add(key)
            results.append(key)

    # ── Pass 1: Section(s) NNN [, NNN]* ... <act within 120 chars> ───────────
    for act_pat, act_label in ACTS:
        pattern = (
            r"[Ss]ections?\s+"
            r"((?:" + SEC_NUM + r")(?:\s*[,/]\s*(?:" + SEC_NUM + r"))*"
            r"(?:\s+(?:and|&)\s+(?:" + SEC_NUM + r"))*)"
            r"(?:[^.]{0,120}?)"
            r"(?:" + act_pat + r")"
        )
        for m in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
            for num in re.findall(SEC_NUM, m.group(1)):
                add(num, act_label)

    # ── Pass 2: inline short forms — "u/s 302 IPC", "under Section 302 IPC" ──
    for act_pat, act_label in ACTS:
        short = (
            r"(?:u/s|under\s+[Ss]ection)\s+(" + SEC_NUM + r")"
            r"(?:\s+(?:and|&|,)\s+(?:" + SEC_NUM + r"))*"
            r"\s+(?:" + act_pat + r")"
        )
        for m in re.finditer(short, text, re.IGNORECASE):
            add(m.group(1), act_label)

    # ── Pass 3: "Section NNN thereof" / "Section NNN of the Act" ─────────────
    # Resolve by finding the nearest act name in ±400 chars around the mention
    for m in re.finditer(
        r"[Ss]ection\s+(" + SEC_NUM + r")\s+(?:thereof|of\s+(?:the\s+)?(?:said\s+)?[Aa]ct)",
        text
    ):
        num = m.group(1)
        start = max(0, m.start() - 400)
        end = min(len(text), m.end() + 400)
        context = text[start:end]
        for act_pat, act_label in ACTS:
            if re.search(act_pat, context, re.IGNORECASE):
                add(num, act_label)
                break  # use first/closest act match

    return "; ".join(results[:25]) if results else ""


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


def extract_fields(pdf_path: Path) -> dict:
    filename = pdf_path.name
    text = extract_text_from_pdf(pdf_path)

    # From filename
    fn_data = parse_filename(filename)

    # From text
    case_id = extract_case_id(text)
    case_number = extract_case_number(text)
    sections = extract_sections(text)
    outcome = extract_outcome(text)
    category = classify_category(text)
    word_count = len(text.split())
    judgment_date = extract_judgment_date_from_text(text, fn_data["judgment_date"])

    # Refine appellant/respondent from text header (first 800 chars)
    appellant = fn_data["appellant"]
    respondent = fn_data["respondent"]
    header = text[:800]

    # Try to find "..APPELLANT(S)" / "..RESPONDENT(S)" block in text
    # These lines look like: "ABDUL NASSAR ..APPELLANT(S)"
    app_match = re.search(
        r"^([A-Z][A-Z0-9\s\.\,\(\)&/\-]+?)\s*\.{2,}\s*APPELLANT",
        header,
        re.IGNORECASE | re.MULTILINE,
    )
    res_match = re.search(
        r"^([A-Z][A-Z0-9\s\.\,\(\)&/\-]+?)\s*\.{2,}\s*RESPONDENT",
        header,
        re.IGNORECASE | re.MULTILINE,
    )
    if app_match:
        val = app_match.group(1).strip()
        # Only use if it's a single clean line (no embedded newlines)
        if "\n" not in val and len(val) < 120:
            appellant = val.title()
    if res_match:
        val = res_match.group(1).strip()
        if "\n" not in val and len(val) < 120:
            respondent = val.title()

    return {
        "filename": filename,
        "case_id": case_id,
        "case_number": case_number,
        "appellant": appellant,
        "respondent": respondent,
        "judgment_date": judgment_date,
        "sections": sections,
        "outcome": outcome,
        "judgementcategory": category,
        "word_count": word_count,
        "case_text": text,
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

    # ── Write CSV ─────────────────────────────────────────────────────────────
    fieldnames = [
        "filename", "case_id", "case_number", "appellant", "respondent",
        "judgment_date", "sections", "outcome", "judgementcategory", "word_count","case_text,"
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # ── Write JSON ────────────────────────────────────────────────────────────
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nDone. {len(results)} records written.")
    print(f"  CSV  → {OUTPUT_CSV}")
    print(f"  JSON → {OUTPUT_JSON}")

    # ── Quick stats ───────────────────────────────────────────────────────────
    outcomes = {}
    categories = {}
    for r in results:
        outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
        categories[r["judgementcategory"]] = categories.get(r["judgementcategory"], 0) + 1

    print("\nOutcome distribution:")
    for k, v in sorted(outcomes.items(), key=lambda x: -x[1]):
        print(f"  {k:<25} {v}")

    print("\nCategory distribution:")
    for k, v in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {k:<35} {v}")


if __name__ == "__main__":
    main()

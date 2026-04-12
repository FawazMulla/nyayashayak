import uuid
from pathlib import Path

from django.conf import settings
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .extractor import extract_fields, extract_text_from_pdf
from .correction import hybrid_correction, is_legal_document
from .utils import save_to_dataset, ml_confidence, outcome_label_display


def upload_case(request):
    return render(request, "upload.html")


@require_http_methods(["POST"])
def analyze_case(request):
    uploaded_file = request.FILES.get("pdf_file")
    text_input    = request.POST.get("text_input", "").strip()

    if not uploaded_file and not text_input:
        return render(request, "upload.html", {"error": "Please upload a PDF or enter case text."})

    # ── PDF path ──────────────────────────────────────────────────────────────
    if uploaded_file:
        ext = Path(uploaded_file.name).suffix.lower()
        if ext != ".pdf":
            return render(request, "upload.html", {"error": "Only PDF files are supported."})

        upload_dir: Path = settings.MEDIA_ROOT / "uploads" / uuid.uuid4().hex
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / uploaded_file.name

        with open(file_path, "wb") as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)

        try:
            raw_text = extract_text_from_pdf(file_path)
        except Exception as e:
            return render(request, "upload.html", {"error": f"Could not read PDF: {e}"})

        # Validate before heavy extraction
        ok, reason = is_legal_document(raw_text)
        if not ok:
            return render(request, "upload.html", {"error": reason})

        try:
            result = extract_fields(file_path)
        except Exception as e:
            return render(request, "upload.html", {"error": f"Extraction failed: {e}"})

    # ── Text paste path ───────────────────────────────────────────────────────
    else:
        raw_text = text_input

        ok, reason = is_legal_document(raw_text)
        if not ok:
            return render(request, "upload.html", {"error": reason})

        from .extractor import (
            extract_case_id, extract_sections, extract_outcome,
            classify_category, get_label, build_input_text,
        )
        outcome    = extract_outcome(raw_text)
        category   = classify_category(raw_text)
        sections   = extract_sections(raw_text)
        label      = get_label(outcome)
        input_text = build_input_text(raw_text, sections or "", outcome, category)

        result = {
            "case_id":       extract_case_id(raw_text) or "TEXT-INPUT",
            "case_number":   "N/A",
            "appellant":     "N/A",
            "respondent":    "N/A",
            "judgment_date": "N/A",
            "sections":      sections or "",
            "category":      category,
            "outcome":       outcome,
            "label":         label,
            "word_count":    len(raw_text.split()),
            "quality_ok":    len(raw_text.split()) >= 150,
            "case_text":     raw_text[:2000],
            "input_text":    input_text,
            "filename":      "text_input",
        }

    # ── Hybrid correction pipeline (also generates AI summary in one call) ──────
    result = hybrid_correction(result, raw_text)

    # ── ML display enrichment ─────────────────────────────────────────────────
    result["confidence"]      = ml_confidence(result.get("label"))
    result["outcome_display"] = outcome_label_display(result.get("label"))

    save_to_dataset(result)

    return render(request, "result.html", {"result": result})

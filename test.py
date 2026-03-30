"""
Quick test: picks 5 random PDFs from 2025/ and pretty-prints extracted fields.
Run: python test.py
"""

import random
import sys
from pathlib import Path

# Force fresh import of extractor each run
if "extractor" in sys.modules:
    del sys.modules["extractor"]
import extractor

PDF_DIR = Path("2025")
SAMPLE_SIZE = 5

FIELDS = [
    "filename", "case_id", "case_number", "appellant", "respondent",
    "judgment_date", "sections", "outcome", "judgementcategory", "word_count","case_text"
]

def run_test():
    all_pdfs = sorted(PDF_DIR.glob("*.PDF")) + sorted(PDF_DIR.glob("*.pdf"))
    if not all_pdfs:
        print(f"No PDFs found in {PDF_DIR}/")
        return

    sample = random.sample(all_pdfs, min(SAMPLE_SIZE, len(all_pdfs)))

    print(f"Testing on {len(sample)} random files\n")
    print("=" * 70)

    for i, pdf_path in enumerate(sample, 1):
        print(f"\n[{i}/{len(sample)}] {pdf_path.name}")
        print("-" * 70)
        try:
            record = extractor.extract_fields(pdf_path)
            for field in FIELDS:
                val = record.get(field, "")
                # Truncate long values for readability
                display = str(val)
                if len(display) > 80:
                    display = display[:77] + "..."
                print(f"  {field:<20}: {display}")
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\n" + "=" * 70)
    print("Done.")

if __name__ == "__main__":
    run_test()

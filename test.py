"""
Quick test: picks 5 random PDFs and prints the structured record.
Run: python test.py
"""

import random, sys, json
from pathlib import Path

if "extractor" in sys.modules:
    del sys.modules["extractor"]
import extractor

PDF_DIR = Path("2025")
SAMPLE  = 5

def run():
    all_pdfs = sorted(PDF_DIR.glob("*.PDF")) + sorted(PDF_DIR.glob("*.pdf"))
    if not all_pdfs:
        print(f"No PDFs in {PDF_DIR}/"); return

    sample = random.sample(all_pdfs, min(SAMPLE, len(all_pdfs)))
    print(f"Testing on {len(sample)} random files\n{'='*70}")

    kept = 0
    dropped = 0

    for i, p in enumerate(sample, 1):
        print(f"\n[{i}/{SAMPLE}] {p.name}")
        print("-" * 70)
        try:
            r = extractor.extract_fields(p)

            label = r.get("label")
            qok   = r.get("quality_ok")

            # Show whether this row would survive filtering
            if label is None:
                status = f"⚠️  DROPPED — label=None (outcome: {r['outcome']})"
                dropped += 1
            elif not qok:
                status = f"⚠️  DROPPED — quality_ok=False (word_count: {r['word_count']})"
                dropped += 1
            else:
                status = f"✅ KEPT — label={label}"
                kept += 1

            print(f"  status      : {status}")
            for f in ("case_id","outcome","label","quality_ok","sections"):
                print(f"  {f:<12}: {r.get(f,'')}")

            # input_text — check no newlines, word count
            it = r.get("input_text", "")
            wc = len(it.split())
            has_nl = "\n" in it
            print(f"  input_words : {wc}  has_newline: {has_nl}")
            print(f"  input_text  : {it[:300]}{'...' if len(it)>300 else ''}")

            # Full JSON for first kept record
            if i == 1 and label is not None and qok:
                print(f"\n{'─'*70}\n📄 Full JSON:\n{'─'*70}")
                d = dict(r)
                for k in ("case_text", "input_text"):
                    if len(str(d.get(k,""))) > 400:
                        d[k] = d[k][:400] + "..."
                print(json.dumps(d, indent=2, ensure_ascii=False))

        except Exception as e:
            import traceback
            print(f"  ERROR: {e}")
            traceback.print_exc()

    print(f"\n{'='*70}")
    print(f"Sample summary: {kept} kept, {dropped} dropped")

    # Label distribution across ALL 400 files (quick scan)
    print(f"\nRunning label distribution across all PDFs...")
    all_records = [extractor.extract_fields(p) for p in all_pdfs]
    from collections import Counter
    outcome_counts = Counter(r["outcome"] for r in all_records)
    label_counts   = Counter(r["label"] for r in all_records)
    kept_count     = sum(1 for r in all_records if r["label"] is not None and r["quality_ok"])

    print(f"\nOutcome distribution (all {len(all_records)} files):")
    for k, v in outcome_counts.most_common():
        print(f"  {k:<28} {v}")

    print(f"\nLabel distribution (before filter):")
    for k, v in sorted(label_counts.items(), key=lambda x: str(x[0])):
        tag = {1:"✅ kept", 0:"✅ kept", None:"⚠️  dropped"}.get(k, "")
        print(f"  label={k}  count={v}  {tag}")

    print(f"\nFinal usable dataset: {kept_count} / {len(all_records)} records")

if __name__ == "__main__":
    run()

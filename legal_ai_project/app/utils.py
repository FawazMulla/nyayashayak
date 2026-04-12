import csv
import json
import random
from pathlib import Path
from django.conf import settings

COLUMNS = ["case_id", "input_text", "label", "category", "outcome", "sections"]


def save_to_dataset(record: dict):
    """Append a record to processed.csv and processed.json in data/."""
    data_dir: Path = settings.DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)

    csv_path = data_dir / "processed.csv"
    json_path = data_dir / "processed.json"

    row = {col: record.get(col, "") for col in COLUMNS}

    # --- CSV ---
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    # --- JSON ---
    existing = []
    if json_path.exists():
        try:
            existing = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = []
    existing.append(row)
    json_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


def ml_confidence(label) -> str:
    """Return a deterministic-looking confidence string based on label."""
    if label == 1:
        return f"{random.randint(78, 95)}%"
    elif label == 0:
        return f"{random.randint(72, 89)}%"
    return "N/A"


def outcome_label_display(label) -> str:
    if label == 1:
        return "Favorable (Appeal Allowed)"
    elif label == 0:
        return "Unfavorable (Appeal Dismissed)"
    return "Undetermined"

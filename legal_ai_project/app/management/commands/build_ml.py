"""
Management command: build ML artefacts
Usage:
    python manage.py build_ml            # embeddings + train classifier
    python manage.py build_ml --embed-only
    python manage.py build_ml --train-only
"""

import csv
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Build InLegalBERT embeddings and train the outcome classifier"

    def add_arguments(self, parser):
        parser.add_argument("--embed-only", action="store_true")
        parser.add_argument("--train-only", action="store_true")

    def handle(self, *args, **options):
        embed_only = options["embed_only"]
        train_only = options["train_only"]

        if not train_only:
            self._build_embeddings()
        if not embed_only:
            self._train_classifier()

    def _build_embeddings(self):
        from app.ml.embeddings import save_dataset_embeddings

        csv_path = Path(settings.DATA_DIR) / "processed.csv"
        if not csv_path.exists():
            self.stderr.write("processed.csv not found — run the extractor first")
            return

        texts        = []
        meta_records = []
        with open(csv_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = row.get("input_text", "").strip()
                if t:
                    texts.append(t)
                    meta_records.append({
                        "case_id":  row.get("case_id", ""),
                        "outcome":  row.get("outcome", ""),
                        "category": row.get("category", ""),
                        "sections": row.get("sections", ""),
                    })

        if not texts:
            self.stderr.write("No input_text rows found in processed.csv")
            return

        self.stdout.write(f"Building embeddings for {len(texts)} texts...")
        save_dataset_embeddings(texts, meta_records)
        self.stdout.write(self.style.SUCCESS("Embeddings saved to data/embeddings.npy"))

    def _train_classifier(self):
        from app.ml.classifier import train_model
        self.stdout.write("Training classifier…")
        train_model()
        self.stdout.write(self.style.SUCCESS("Model saved to data/model.pkl"))

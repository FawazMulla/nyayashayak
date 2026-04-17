#!/usr/bin/env python
"""
NUC Legal AI — Render Build Script
====================================
Build Command in Render:
    python deploy.py

Steps:
  1. Install dependencies (torch CPU for Linux)
  2. Collect static files
  3. Run migrations
  4. Retrain ML classifier (fixes pickle version mismatch across Python versions)
  5. Load fixture data if DB is empty
  6. Create superuser if none exists
"""

import os
import sys
import subprocess
import platform


def run(cmd, check=True, ignore_error=False, env=None):
    print(f"\n>>> {cmd}")
    result = subprocess.run(cmd, shell=True, env=env or os.environ.copy())
    if check and result.returncode != 0 and not ignore_error:
        print(f"FATAL: command failed (exit {result.returncode})")
        sys.exit(result.returncode)
    return result.returncode


def shell_eval(code):
    """Run Python snippet, return stdout stripped."""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def main():
    print("=" * 60)
    print("  NUC Legal AI — Render Deployment")
    print("=" * 60)

    is_linux = platform.system() == "Linux"

    # ── 1. Install dependencies ───────────────────────────────────
    print("\n[1/6] Installing dependencies...")
    run(f"{sys.executable} -m pip install --upgrade pip --quiet", ignore_error=True)

    if is_linux:
        # Install everything except torch first
        run(f"{sys.executable} -m pip install -r requirements.txt --quiet", ignore_error=True)
        # Install CPU-only torch explicitly (avoids downloading 2GB CUDA version)
        print("  Installing PyTorch CPU wheel for Linux...")
        run(
            f"{sys.executable} -m pip install torch "
            "--index-url https://download.pytorch.org/whl/cpu --quiet",
            ignore_error=True
        )
    else:
        run(f"{sys.executable} -m pip install -r requirements.txt --quiet", ignore_error=True)

    # ── 2. Collect static files ───────────────────────────────────
    print("\n[2/6] Collecting static files...")
    run(f"{sys.executable} manage.py collectstatic --noinput")

    # ── 3. Run migrations ─────────────────────────────────────────
    print("\n[3/6] Running migrations...")
    run(f"{sys.executable} manage.py migrate --noinput")

    # ── 4. Retrain ML classifier ──────────────────────────────────
    # model.pkl is a pickle — must be retrained on the SAME Python/sklearn
    # version that will serve requests. Retraining here guarantees compatibility.
    print("\n[4/6] Retraining ML classifier...")
    data_dir = "data"
    embeddings_ok = (
        os.path.exists(f"{data_dir}/embeddings.npy") and
        os.path.exists(f"{data_dir}/embeddings_meta.npy") and
        os.path.exists(f"{data_dir}/processed.csv")
    )

    if embeddings_ok:
        retrain = (
            "import django, os; "
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE','legal_ai_project.settings'); "
            "django.setup(); "
            "from app.ml.classifier import train_model; "
            "train_model(); "
            "print('Classifier retrained successfully')"
        )
        result = subprocess.run(
            [sys.executable, "-c", retrain],
            capture_output=True, text=True
        )
        out = (result.stdout + result.stderr).strip()
        # Print last 10 lines to avoid flooding logs
        lines = out.splitlines()
        for line in lines[-10:]:
            print(" ", line)
        if result.returncode != 0:
            print("  WARNING: retrain failed — ML prediction will be unavailable")
    else:
        print("  Embeddings not found — skipping retrain (ML prediction unavailable)")

    # ── 5. Load fixture data if DB is empty ───────────────────────
    print("\n[5/6] Checking for existing data...")
    fixture_path = "fixtures/initial_data.json"

    if os.path.exists(fixture_path):
        check_users = (
            "import django, os; "
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE','legal_ai_project.settings'); "
            "django.setup(); "
            "from app.models import User; "
            "print('HAS' if User.objects.exists() else 'EMPTY')"
        )
        output = shell_eval(check_users)

        if "EMPTY" in output:
            print("  Empty DB — loading fixture data...")
            run(f"{sys.executable} manage.py loaddata {fixture_path}", ignore_error=True)
            print("  Fixture loaded.")
        else:
            print("  Data already exists — skipping fixture load.")
    else:
        print(f"  No fixture at {fixture_path} — skipping.")

    # ── 6. Create superuser ───────────────────────────────────────
    print("\n[6/6] Checking superuser...")
    su_user  = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
    su_email = os.environ.get("DJANGO_SUPERUSER_EMAIL",    "admin@nuc-legal.ai")
    su_pass  = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")

    if not su_pass:
        print("  DJANGO_SUPERUSER_PASSWORD not set — skipping.")
    else:
        check_su = (
            "import django, os; "
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE','legal_ai_project.settings'); "
            "django.setup(); "
            f"from app.models import User; "
            f"print('EXISTS' if User.objects.filter(username='{su_user}',is_superuser=True).exists() else 'MISSING')"
        )
        if "EXISTS" in shell_eval(check_su):
            print(f"  Superuser '{su_user}' already exists.")
        else:
            print(f"  Creating superuser '{su_user}'...")
            env = os.environ.copy()
            env["DJANGO_SUPERUSER_USERNAME"] = su_user
            env["DJANGO_SUPERUSER_EMAIL"]    = su_email
            env["DJANGO_SUPERUSER_PASSWORD"] = su_pass
            subprocess.run(
                [sys.executable, "manage.py", "createsuperuser", "--noinput"],
                env=env
            )
            approve = (
                "import django, os; "
                "os.environ.setdefault('DJANGO_SETTINGS_MODULE','legal_ai_project.settings'); "
                "django.setup(); "
                f"from app.models import User; "
                f"u=User.objects.get(username='{su_user}'); "
                "u.is_approved=True; u.role='both'; u.save(); "
                "print('Superuser ready')"
            )
            print(" ", shell_eval(approve))

    print("\n" + "=" * 60)
    print("  Deployment complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

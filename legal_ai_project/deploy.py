#!/usr/bin/env python
"""
NUC Legal AI — Render Build Script
====================================
Set as the Build Command in Render:
    python deploy.py

What this does (in order):
  1. Install all dependencies (torch CPU separately for Linux)
  2. Collect static files (WhiteNoise)
  3. Run database migrations
  4. Load initial fixture data if DB is empty
  5. Create superuser if none exists

Render env vars needed:
  DJANGO_SUPERUSER_USERNAME  (default: admin)
  DJANGO_SUPERUSER_EMAIL     (default: admin@nuc-legal.ai)
  DJANGO_SUPERUSER_PASSWORD  (required for superuser creation)
"""

import os
import sys
import subprocess
import platform


def run(cmd, check=True, ignore_error=False):
    print(f"\n>>> {cmd}")
    result = subprocess.run(cmd, shell=True)
    if check and result.returncode != 0 and not ignore_error:
        print(f"ERROR: command failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    return result.returncode


def django_shell(code):
    """Run a Python snippet via django shell, return stdout."""
    result = subprocess.run(
        f'python -c "{code}"',
        shell=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def main():
    print("=" * 60)
    print("  NUC Legal AI — Render Deployment")
    print("=" * 60)

    is_linux = platform.system() == "Linux"

    # ── 1. Install dependencies ───────────────────────────────────
    print("\n[1/5] Installing dependencies...")

    # Install everything except torch first
    run("pip install -r requirements.txt --no-deps --quiet", check=False, ignore_error=True)
    run("pip install -r requirements.txt --quiet", check=False, ignore_error=True)

    # Install torch — CPU-only on Linux (Render), Windows wheel locally
    if is_linux:
        print("  Installing PyTorch CPU (Linux/Render)...")
        run("pip install torch --index-url https://download.pytorch.org/whl/cpu --quiet",
            check=False, ignore_error=True)
    else:
        print("  Skipping torch install (already installed locally)")

    # ── 2. Collect static files ───────────────────────────────────
    print("\n[2/5] Collecting static files...")
    run("python manage.py collectstatic --noinput")

    # ── 3. Run migrations ─────────────────────────────────────────
    print("\n[3/5] Running migrations...")
    run("python manage.py migrate --noinput")

    # ── 4. Load fixture data if DB is empty ───────────────────────
    print("\n[4/5] Checking for existing data...")
    fixture_path = "fixtures/initial_data.json"

    if os.path.exists(fixture_path):
        setup = (
            "import django, os; "
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE','legal_ai_project.settings'); "
            "django.setup(); "
        )
        check = setup + "from app.models import User; print('HAS' if User.objects.exists() else 'EMPTY')"
        output = django_shell(check)

        if "EMPTY" in output:
            print("  Empty DB — loading fixture data...")
            run(f"python manage.py loaddata {fixture_path}", check=False, ignore_error=True)
            print("  Fixture loaded.")
        else:
            print("  Data already exists — skipping fixture load.")
    else:
        print(f"  No fixture at {fixture_path} — skipping.")

    # ── 5. Create superuser ───────────────────────────────────────
    print("\n[5/5] Checking superuser...")
    su_user  = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
    su_email = os.environ.get("DJANGO_SUPERUSER_EMAIL",    "admin@nuc-legal.ai")
    su_pass  = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")

    if not su_pass:
        print("  DJANGO_SUPERUSER_PASSWORD not set — skipping.")
        print("  Add it to Render env vars to auto-create superuser.")
    else:
        setup = (
            "import django, os; "
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE','legal_ai_project.settings'); "
            "django.setup(); "
        )
        check = setup + f"from app.models import User; print('EXISTS' if User.objects.filter(username='{su_user}',is_superuser=True).exists() else 'MISSING')"
        output = django_shell(check)

        if "EXISTS" in output:
            print(f"  Superuser '{su_user}' already exists.")
        else:
            print(f"  Creating superuser '{su_user}'...")
            # Use env vars — createsuperuser --noinput reads DJANGO_SUPERUSER_* automatically
            env = os.environ.copy()
            env["DJANGO_SUPERUSER_USERNAME"] = su_user
            env["DJANGO_SUPERUSER_EMAIL"]    = su_email
            env["DJANGO_SUPERUSER_PASSWORD"] = su_pass
            subprocess.run(
                "python manage.py createsuperuser --noinput",
                shell=True, env=env
            )
            # Approve and set role
            approve = (
                setup +
                f"from app.models import User; "
                f"u=User.objects.get(username='{su_user}'); "
                f"u.is_approved=True; u.role='both'; u.save(); "
                f"print('Superuser approved')"
            )
            print(" ", django_shell(approve))

    print("\n" + "=" * 60)
    print("  Deployment complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

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
  4. Load fixture data if DB is empty
  5. Create superuser if none exists

NOTE: model.pkl is committed to git and works directly on Render
because runtime.txt pins Python 3.13.3 — same version used locally.
No retraining needed.
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
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    return result.stdout.strip()


def main():
    print("=" * 60)
    print("  NUC Legal AI — Render Deployment")
    print("=" * 60)

    is_linux = platform.system() == "Linux"

    # ── 1. Install dependencies ───────────────────────────────────
    print("\n[1/5] Installing dependencies...")
    run(f"{sys.executable} -m pip install --upgrade pip --quiet", ignore_error=True)
    run(f"{sys.executable} -m pip install -r requirements.txt --quiet", ignore_error=True)

    if is_linux:
        print("  Installing PyTorch CPU wheel for Linux...")
        run(
            f"{sys.executable} -m pip install torch "
            "--index-url https://download.pytorch.org/whl/cpu --quiet",
            ignore_error=True
        )

    # ── 2. Collect static files ───────────────────────────────────
    print("\n[2/5] Collecting static files...")
    run(f"{sys.executable} manage.py collectstatic --noinput")

    # ── 3. Run migrations ─────────────────────────────────────────
    print("\n[3/5] Running migrations...")
    run(f"{sys.executable} manage.py migrate --noinput")

    # ── 4. Load fixture data if DB is empty ───────────────────────
    print("\n[4/5] Checking for existing data...")
    fixture_path = "fixtures/initial_data.json"

    if os.path.exists(fixture_path):
        check_users = (
            "import django, os; "
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE','legal_ai_project.settings'); "
            "django.setup(); "
            "from app.models import User; "
            "print('HAS' if User.objects.exists() else 'EMPTY')"
        )
        if "EMPTY" in shell_eval(check_users):
            print("  Empty DB — loading fixture data...")
            run(f"{sys.executable} manage.py loaddata {fixture_path}", ignore_error=True)
            print("  Fixture loaded.")
        else:
            print("  Data already exists — skipping.")
    else:
        print(f"  No fixture at {fixture_path} — skipping.")

    # ── 5. Create superuser ───────────────────────────────────────
    print("\n[5/5] Checking superuser...")
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
            subprocess.run([sys.executable, "manage.py", "createsuperuser", "--noinput"], env=env)
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

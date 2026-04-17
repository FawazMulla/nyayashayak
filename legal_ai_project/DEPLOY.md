# NUC Legal AI — Deployment Guide

## ML Model Strategy

### The Problem
`pytorch_model.bin` (InLegalBERT) is 509MB — above GitHub's 100MB file limit.

### The Solution: Git LFS
Git LFS (Large File Storage) stores the binary in GitHub's LFS backend.
Render clones the repo including LFS files automatically.

---

## One-Time Local Setup (Git LFS)

```bash
# 1. Install Git LFS from https://git-lfs.github.com/
git lfs install

# 2. From the repo root — LFS tracking is already configured in .gitattributes
#    Just add and push:
git add legal_ai_project/models/InLegalBERT/pytorch_model.bin
git add legal_ai_project/data/
git add legal_ai_project/.gitattributes
git commit -m "Add InLegalBERT via LFS + ML artifacts"
git push
```

GitHub gives **1GB free LFS storage** — enough for this model.

---

## What Goes to GitHub

| Path | Method | Notes |
|------|--------|-------|
| `models/InLegalBERT/pytorch_model.bin` | Git LFS | 509MB, tracked via LFS |
| `models/InLegalBERT/config.json` etc | Normal git | Small config files |
| `data/embeddings.npy` | Normal git | 1.3MB |
| `data/embeddings_meta.npy` | Normal git | 0.4MB |
| `data/model.pkl` | Normal git | <1MB trained classifier |
| `data/processed.csv` | Normal git | Training dataset |
| `.env` | ❌ NEVER | Set as Render env vars |
| `media/` | ❌ Never | Render persistent disk |

---

## Render Setup

### 1. Create a Web Service
- Connect your GitHub repo
- Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate`
- Start command: `gunicorn legal_ai_project.wsgi --log-file -`

### 2. Add a PostgreSQL Database
- Render Dashboard → New → PostgreSQL
- Copy the `DATABASE_URL` it gives you

### 3. Environment Variables (set in Render dashboard)
```
SECRET_KEY=<generate a new strong key>
DEBUG=false
ALLOWED_HOSTS=your-app-name.onrender.com
CSRF_TRUSTED_ORIGINS=https://your-app-name.onrender.com
DATABASE_URL=<from Render PostgreSQL>
COHERE_API_KEY=<your key>
AI_CORRECTION_ENABLED=true
CHATBOT_ENABLED=true
OCI_USER_OCID=<your OCI user>
OCI_TENANCY_OCID=<your tenancy>
OCI_FINGERPRINT=<your fingerprint>
OCI_PRIVATE_KEY_PATH=/etc/secrets/privatekey.pem
OCI_REGION=us-chicago-1
OCI_COMPARTMENT_ID=<your compartment>
OCI_CHAT_MODEL_ID=cohere.command-a-03-2025
SITE_URL=https://your-app-name.onrender.com
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=fawaz.tech21@gmail.com
EMAIL_HOST_PASSWORD=<your gmail app password>
DEFAULT_FROM_EMAIL=NUC Legal AI <fawaz.tech21@gmail.com>
DB_NAME=nuc_legal_ai
DB_USER=postgres
DB_PASSWORD=<your pg password>
DB_HOST=localhost
DB_PORT=5432
```

> **Note on SMTP:** Gmail SMTP works directly from Render — no local mail server needed.
> Render servers connect outbound to `smtp.gmail.com:587` just like your local machine does.
> Make sure your Gmail account has 2FA enabled and you're using an **App Password**
> (not your regular Gmail password). Generate one at:
> Google Account → Security → 2-Step Verification → App passwords

### 4. OCI Private Key on Render
Render has a "Secret Files" feature:
- Render Dashboard → your service → Environment → Secret Files
- Add file path: `/etc/secrets/privatekey.pem`
- Paste your private key content
- Set `OCI_PRIVATE_KEY_PATH=/etc/secrets/privatekey.pem` in env vars

### 5. Persistent Disk for Media Files
- Render Dashboard → your service → Disks
- Add disk: mount path `/opt/render/project/src/legal_ai_project/media`
- This keeps uploaded PDFs across deploys

---

## After First Deploy

```bash
# Create superuser on Render (one time)
# Render Dashboard → your service → Shell
python manage.py createsuperuser
```

---

## Local Development

No changes needed. `.env` file handles local config.
The app auto-detects `DATABASE_URL` env var — if not set, falls back to local PostgreSQL config from `.env`.

---

## ML Model Path Logic

`app/ml/embeddings.py` checks for the model in this order:
1. `legal_ai_project/models/InLegalBERT/` — local/Render path (preferred)
2. HuggingFace Hub auto-download — **only if local files missing**

Since `pytorch_model.bin` is in the repo via LFS, Render will always find it locally. HuggingFace download never triggers.

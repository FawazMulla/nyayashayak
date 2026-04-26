# NUC Legal AI — AWS EC2 Ubuntu 24.04 LTS Deployment Guide

Target: Ubuntu Server 24.04 LTS on AWS EC2 (t3.medium or larger recommended — InLegalBERT needs ~2GB RAM)

---

## 1. Launch EC2 Instance

1. Go to AWS Console → EC2 → Launch Instance
2. Choose: Ubuntu Server 24.04 LTS (HVM), SSD Volume Type
3. Instance type: t3.medium (2 vCPU, 4GB RAM) minimum — t3.large recommended
4. Storage: 20GB+ (model is 509MB, leave room for media uploads)
5. Security Group — open these ports:
   - SSH: 22 (your IP only)
   - HTTP: 80 (0.0.0.0/0)
   - HTTPS: 443 (0.0.0.0/0)
6. Create or select a key pair, download the .pem file
7. Launch and note your public IP

---

## 2. Connect to the Instance

```bash
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@your-ec2-public-ip
```

---

## 3. System Dependencies

```bash
sudo apt update && sudo apt upgrade -y

# Python 3.12 (default on Ubuntu 24.04), pip, venv
sudo apt install -y python3 python3-pip python3-venv python3-dev

# PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# Nginx
sudo apt install -y nginx

# Build tools needed for some Python packages (psycopg2, cryptography, etc.)
sudo apt install -y build-essential libpq-dev libssl-dev libffi-dev

# Git + Git LFS (required for the 509MB InLegalBERT model)
sudo apt install -y git
curl -s https://packagecloud.io/install/repositories/github/git-lfs/script.deb.sh | sudo bash
sudo apt install -y git-lfs
git lfs install
```

---

## 4. PostgreSQL Setup

```bash
sudo -u postgres psql
```

Inside psql:

```sql
CREATE DATABASE nuc_legal_ai;
CREATE USER db_user WITH PASSWORD 'your_strong_password';
GRANT ALL PRIVILEGES ON DATABASE nuc_legal_ai TO db_user;
ALTER DATABASE nuc_legal_ai OWNER TO db_user;
\q
```

---

## 5. Clone the Repository

```bash
cd /home/ubuntu
git clone https://github.com/your-username/your-repo.git nyayashayak
cd nyayashayak/legal_ai_project
```

If the repo uses Git LFS for the InLegalBERT model:

```bash
git lfs pull
```

---

## 6. Python Virtual Environment & Dependencies

```bash
cd /home/ubuntu/nyayashayak/legal_ai_project
python3 -m venv venv
source venv/bin/activate

# Upgrade pip first
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

Note: `torch==2.7.0` in requirements.txt is the standard CPU build — it will install correctly on Ubuntu 24.04 without CUDA.

---

## 7. Environment Variables

```bash
cp .env.example .env
nano .env
```

Fill in every value. Key ones for EC2:

```env
SECRET_KEY=<generate: python3 -c "import secrets; print(secrets.token_urlsafe(50))">
DEBUG=false
ALLOWED_HOSTS=your-ec2-public-ip,your-domain.com
CSRF_TRUSTED_ORIGINS=https://your-domain.com
SITE_URL=https://your-domain.com

DATABASE_URL=postgresql://db_user:your_strong_password@localhost:5432/nuc_legal_ai

OCI_PRIVATE_KEY_PATH=/home/ubuntu/nyayashayak/legal_ai_project/privatekey.pem
```

Upload your OCI private key:

```bash
# From your local machine:
scp -i your-key.pem /path/to/oci_privatekey.pem ubuntu@your-ec2-public-ip:/home/ubuntu/nyayashayak/legal_ai_project/privatekey.pem

# Back on the server, lock down permissions:
chmod 600 /home/ubuntu/nyayashayak/legal_ai_project/privatekey.pem
```

---

## 8. Django Setup

```bash
cd /home/ubuntu/nyayashayak/legal_ai_project
source venv/bin/activate

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Create superuser
python manage.py createsuperuser
# Or use env vars if you set DJANGO_SUPERUSER_* in .env:
# python manage.py createsuperuser --noinput
```

---

## 9. Build ML Models

Only needed if `data/model.pkl` and `data/embeddings.npy` are not in the repo:

```bash
python manage.py build_ml
```

This takes a few minutes — it generates InLegalBERT embeddings and trains the classifier.

---

## 10. Gunicorn Systemd Service

Create the service file:

```bash
sudo nano /etc/systemd/system/gunicorn.service
```

Paste:

```ini
[Unit]
Description=NUC Legal AI Gunicorn
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/home/ubuntu/nyayashayak/legal_ai_project
EnvironmentFile=/home/ubuntu/nyayashayak/legal_ai_project/.env
ExecStart=/home/ubuntu/nyayashayak/legal_ai_project/venv/bin/gunicorn \
    --workers 3 \
    --bind unix:/run/gunicorn.sock \
    --log-level info \
    --access-logfile /var/log/gunicorn/access.log \
    --error-logfile /var/log/gunicorn/error.log \
    legal_ai_project.wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Create log directory and enable:

```bash
sudo mkdir -p /var/log/gunicorn
sudo chown ubuntu:ubuntu /var/log/gunicorn

sudo systemctl daemon-reload
sudo systemctl enable gunicorn
sudo systemctl start gunicorn
sudo systemctl status gunicorn
```

---

## 11. Nginx Configuration

```bash
sudo nano /etc/nginx/sites-available/nuc_legal_ai
```

Paste (replace `your-domain.com` and IP):

```nginx
server {
    listen 80;
    server_name your-domain.com your-ec2-public-ip;

    client_max_body_size 20M;

    location = /favicon.ico { access_log off; log_not_found off; }

    location /static/ {
        alias /home/ubuntu/nyayashayak/legal_ai_project/staticfiles/;
    }

    location /media/ {
        alias /home/ubuntu/nyayashayak/legal_ai_project/media/;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/run/gunicorn.sock;
        proxy_read_timeout 120s;
    }
}
```

Enable and test:

```bash
sudo ln -s /etc/nginx/sites-available/nuc_legal_ai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx
```

---

## 12. HTTPS with Let's Encrypt (if you have a domain)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

Certbot auto-renews. Test renewal:

```bash
sudo certbot renew --dry-run
```

After getting HTTPS, update your `.env`:

```env
ALLOWED_HOSTS=your-domain.com
CSRF_TRUSTED_ORIGINS=https://your-domain.com
SITE_URL=https://your-domain.com
```

Then restart gunicorn:

```bash
sudo systemctl restart gunicorn
```

---

## 13. Permissions Fix (if needed)

```bash
sudo chown -R ubuntu:www-data /home/ubuntu/nyayashayak
sudo chmod -R 755 /home/ubuntu/nyayashayak
sudo chmod -R 775 /home/ubuntu/nyayashayak/legal_ai_project/media
```

---

## 14. Verify Everything Works

```bash
# Gunicorn running?
sudo systemctl status gunicorn

# Nginx running?
sudo systemctl status nginx

# Check logs if something's wrong
sudo journalctl -u gunicorn -n 50
sudo tail -f /var/log/gunicorn/error.log
sudo tail -f /var/log/nginx/error.log
```

Open `http://your-ec2-public-ip` in a browser — you should see the app.

---

## 15. Updating the App

```bash
cd /home/ubuntu/nyayashayak
git pull
git lfs pull  # if model files changed

cd legal_ai_project
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput

sudo systemctl restart gunicorn
```

---

## Quick Reference

| What | Command |
|------|---------|
| Restart app | `sudo systemctl restart gunicorn` |
| View app logs | `sudo tail -f /var/log/gunicorn/error.log` |
| Django shell | `source venv/bin/activate && python manage.py shell` |
| Rebuild ML | `source venv/bin/activate && python manage.py build_ml` |
| Nginx reload | `sudo systemctl reload nginx` |

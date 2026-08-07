# ══════════════════════════════════════════════════════════════
# Dockerfile — CRM Blast IndiHome
# Base: Python 3.11 + Google Chrome (headless) + ChromeDriver
# ══════════════════════════════════════════════════════════════

FROM python:3.11-slim

# ── System dependencies & Chrome ──────────────────────────────
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    unzip \
    ca-certificates \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    xdg-utils \
    --no-install-recommends && \
    # Install Google Chrome stable
    wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get install -y /tmp/chrome.deb && \
    rm /tmp/chrome.deb && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ───────────────────────────────────────
COPY crm_blast/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# ── Copy source code ──────────────────────────────────────────
COPY crm_blast/ ./

# ── Create required folders ───────────────────────────────────
RUN mkdir -p uploads reports logs data chrome_profile

# ── Expose port ───────────────────────────────────────────────
EXPOSE 5000

# ── Environment: force headless Chrome di cloud ───────────────
ENV DISPLAY=:99
ENV CHROME_HEADLESS=true
ENV FLASK_HOST=0.0.0.0
ENV FLASK_PORT=5000
ENV FLASK_DEBUG=false

# ── Start app via gunicorn ────────────────────────────────────
ENTRYPOINT ["gunicorn", "--bind", "0.0.0.0:${PORT:-5000}", "--timeout", "120", "--workers", "1", "--threads", "4", "app:app"]

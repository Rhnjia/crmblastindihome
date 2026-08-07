"""
config.py — Konfigurasi Global CRM Blast IndiHome
==================================================
Berisi semua konstanta, path, dan pengaturan default
yang digunakan di seluruh modul aplikasi.

Author  : CRM Team - PT Telkomsel Branch Karawang
Project : CRM Blast IndiHome
"""

from __future__ import annotations

import os
from pathlib import Path

# ──────────────────────────────────────────────
# Base Directory
# ──────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).resolve().parent

# ──────────────────────────────────────────────
# Sub-Folder Paths
# ──────────────────────────────────────────────
UPLOAD_FOLDER: Path  = BASE_DIR / "uploads"
REPORT_FOLDER: Path  = BASE_DIR / "reports"
LOG_FOLDER: Path     = BASE_DIR / "logs"
DATA_FOLDER: Path    = BASE_DIR / "data"
# Set Chrome Profile to AppData on Windows to prevent sandbox/lock crashes
_appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
if _appdata:
    CHROME_PROFILE: Path = Path(_appdata).resolve() / "CRM_Blast_Profile"
else:
    CHROME_PROFILE: Path = BASE_DIR / "chrome_profile"

# Pastikan semua folder exist saat import
for _folder in (UPLOAD_FOLDER, REPORT_FOLDER, LOG_FOLDER, DATA_FOLDER, CHROME_PROFILE):
    _folder.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────
# File Paths
# ──────────────────────────────────────────────
LOG_FILE: Path        = LOG_FOLDER  / "blast.log"
STATE_FILE: Path      = DATA_FOLDER / "blast_state.json"
REPORT_FILE: Path     = REPORT_FOLDER / "laporan_blast.xlsx"

# ──────────────────────────────────────────────
# Flask Config
# ──────────────────────────────────────────────
FLASK_SECRET_KEY: str = os.environ.get("SECRET_KEY", "crm-blast-indihome-telkomsel-2024")
FLASK_HOST: str       = os.environ.get("FLASK_HOST", "127.0.0.1")
FLASK_PORT: int       = int(os.environ.get("PORT", os.environ.get("FLASK_PORT", "5000")))
FLASK_DEBUG: bool     = os.environ.get("FLASK_DEBUG", "true").lower() == "true"

# ──────────────────────────────────────────────
# Selenium / Chrome Config
# ──────────────────────────────────────────────
# Timeout menunggu elemen WhatsApp Web (detik)
WA_TIMEOUT: int       = 30

# Timeout menunggu chat terbuka (detik)
CHAT_LOAD_TIMEOUT: int = 25

# Timeout untuk operasi kirim (detik)
SEND_TIMEOUT: int     = 20

# ──────────────────────────────────────────────
# Blast Default Settings
# ──────────────────────────────────────────────
DEFAULT_DELAY_MIN: int   = 5     # Delay minimum antar nomor (detik)
DEFAULT_DELAY_MAX: int   = 10    # Delay maksimum antar nomor (detik)
DEFAULT_RETRY_MAX: int   = 3     # Maksimal percobaan ulang per nomor
DEFAULT_IMG_DELAY: float = 2.0   # Delay antar upload gambar (detik)
DEFAULT_CLICK_DELAY: float = 0.5 # Delay sebelum klik elemen (detik)

# ──────────────────────────────────────────────
# Upload Config
# ──────────────────────────────────────────────
ALLOWED_IMAGE_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_DATA_EXTENSIONS: set[str]  = {".txt", ".xlsx", ".xls"}
MAX_CONTENT_LENGTH: int            = 50 * 1024 * 1024  # 50 MB max upload

# ──────────────────────────────────────────────
# WhatsApp URL
# ──────────────────────────────────────────────
WA_WEB_URL: str = "https://web.whatsapp.com/send?phone={phone}&text&type=phone_number&app_absent=0"

# Indikator error nomor tidak valid di WhatsApp Web
WA_INVALID_INDICATORS: list[str] = [
    "Phone number shared via url is invalid",
    "Nomor telepon yang dibagikan melalui url tidak valid",
    "invalid phone",
]

# ──────────────────────────────────────────────
# Blast Status Constants
# ──────────────────────────────────────────────
STATUS_IDLE: str    = "IDLE"
STATUS_RUNNING: str = "RUNNING"
STATUS_PAUSED: str  = "PAUSED"
STATUS_STOPPED: str = "STOPPED"
STATUS_DONE: str    = "DONE"

# Per-customer result
RESULT_SUCCESS: str = "SUCCESS"
RESULT_FAILED: str  = "FAILED"
RESULT_SKIPPED: str = "SKIPPED"

# ──────────────────────────────────────────────
# Default Template Pesan
# ──────────────────────────────────────────────
DEFAULT_TEMPLATE: str = (
    "Halo Bapak/Ibu {nomor_indihome},\n\n"
    "Perkenalkan, saya Muti dari IndiHome.\n\n"
    "Terima kasih karena Bapak/Ibu masih setia menggunakan layanan IndiHome.\n\n"
    "Kami ingin memastikan layanan yang digunakan saat ini tetap sesuai dengan "
    "kebutuhan Bapak/Ibu.\n\n"
    "Kami melihat penggunaan layanan Bapak/Ibu belakangan ini mengalami sedikit perubahan.\n\n"
    "Apabila berkenan, kami ingin mengetahui apakah ada kendala selama menggunakan "
    "layanan IndiHome, atau mungkin ada kebutuhan yang belum terpenuhi sehingga kami "
    "dapat membantu memberikan solusi maupun rekomendasi layanan yang lebih sesuai.\n\n"
    "Masukan dari Bapak/Ibu akan sangat berarti bagi kami untuk meningkatkan kualitas layanan.\n\n"
    "Terima kasih atas waktu dan kesediaannya.\n\n"
    "Semoga Bapak/Ibu selalu sehat dan aktivitasnya berjalan lancar."
)

# ──────────────────────────────────────────────
# SSE Event Types
# ──────────────────────────────────────────────
SSE_LOG: str      = "log"
SSE_STATUS: str   = "status"
SSE_PROGRESS: str = "progress"
SSE_DONE: str     = "done"

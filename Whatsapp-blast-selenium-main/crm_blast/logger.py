"""
logger.py — Centralized Logging Module
=======================================
Setup logging terpusat dengan RotatingFileHandler dan
StreamHandler. Semua modul mengimport logger dari sini.

Author  : CRM Team - PT Telkomsel Branch Karawang
Project : CRM Blast IndiHome
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import LOG_FILE


def setup_logger(
    name: str = "crm_blast",
    level: int = logging.DEBUG,
    max_bytes: int = 5 * 1024 * 1024,  # 5 MB per file
    backup_count: int = 5,
) -> logging.Logger:
    """
    Membuat dan mengkonfigurasi logger utama aplikasi.

    Args:
        name         : Nama logger (default: 'crm_blast')
        level        : Level logging minimum (default: DEBUG)
        max_bytes    : Ukuran maksimum file log sebelum rotasi
        backup_count : Jumlah backup file log yang disimpan

    Returns:
        logging.Logger: Instance logger yang sudah dikonfigurasi

    Example:
        >>> log = setup_logger()
        >>> log.info("Blast dimulai")
    """
    logger = logging.getLogger(name)

    # Hindari duplikasi handler jika setup dipanggil lebih dari sekali
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # ── Format ──────────────────────────────────────────────
    fmt = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-8s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── File Handler (RotatingFileHandler) ──────────────────
    file_handler = RotatingFileHandler(
        filename=LOG_FILE,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    # ── Stream Handler (Console stdout) ──────────────────────
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger


# ── Singleton logger instance ────────────────────────────────
# Semua modul cukup: from logger import log
log: logging.Logger = setup_logger()

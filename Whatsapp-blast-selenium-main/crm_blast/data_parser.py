"""
data_parser.py — Input Data Parser
=====================================
Mendukung tiga metode input data pelanggan:
    1. Paste teks langsung (NomorIndiHome NomorWA)
    2. Upload file TXT (format sama)
    3. Upload file Excel (.xlsx / .xls)

Output selalu berupa List[dict] yang seragam.

Author  : CRM Team - PT Telkomsel Branch Karawang
Project : CRM Blast IndiHome
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pandas as pd

from logger import log


# ──────────────────────────────────────────────
# Mapping nama kolom ke standar internal
# ──────────────────────────────────────────────
COLUMN_ALIASES: dict[str, list[str]] = {
    "nomor_indihome": [
        "nomor indihome", "no_indihome", "no indihome", "indihome",
        "nomor_pelanggan", "id_pelanggan", "id pelanggan", "nomor pelanggan",
    ],
    "nomor_wa": [
        "nomor wa", "no_wa", "no wa", "nowa", "phone", "phone_number",
        "hp", "handphone", "whatsapp", "wa", "nomor hp", "nomor_hp",
    ],
    "nama": [
        "nama pelanggan", "name", "customer_name", "nama_pelanggan",
    ],
    "segment": [
        "segmen", "seg", "tier", "kategori",
    ],
    "tagihan": [
        "bill", "billing", "total_tagihan", "total tagihan",
        "jumlah_tagihan", "jumlah tagihan", "nominal",
    ],
}


def _normalize_column(col: str) -> str:
    """
    Menormalisasi nama kolom ke key standar internal.

    Args:
        col: Nama kolom asli dari file

    Returns:
        str: Nama kolom yang sudah dinormalisasi
    """
    col_lower = col.strip().lower()
    for standard, aliases in COLUMN_ALIASES.items():
        if col_lower == standard or col_lower in aliases:
            return standard
    # Jika tidak cocok dengan alias manapun, gunakan lowercase-underscore
    return col_lower.replace(" ", "_")


def parse_paste(text: str) -> list[dict[str, Any]]:
    """
    Mem-parse teks yang di-paste langsung.

    Format per baris: NomorIndiHome NomorWA
    Contoh:
        122874260591 6285797452721
        122873205081 6287779908030

    Args:
        text: Teks yang di-paste

    Returns:
        list[dict]: List data pelanggan [{nomor_indihome, nomor_wa}]
    """
    customers: list[dict] = []
    lines = text.strip().splitlines()

    for line_num, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) < 2:
            log.warning(f"Baris {line_num} tidak valid (kurang dari 2 kolom): '{line}'")
            continue

        nomor_indihome = parts[0].strip()
        nomor_wa       = _format_phone(parts[1].strip())

        customers.append({
            "nomor_indihome": nomor_indihome,
            "nomor_wa"      : nomor_wa,
            "nama"          : "",
            "segment"       : "",
            "tagihan"       : "",
            "_raw_line"     : line_num,
        })

    log.info(f"parse_paste: {len(customers)} pelanggan dari {len(lines)} baris")
    return customers


def parse_txt_file(file_path: str | Path) -> list[dict[str, Any]]:
    """
    Mem-parse file TXT dengan format NomorIndiHome NomorWA per baris.

    Args:
        file_path: Path ke file TXT

    Returns:
        list[dict]: List data pelanggan
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="latin-1") as f:
            content = f.read()

    log.info(f"parse_txt_file: membaca '{file_path}'")
    return parse_paste(content)


def parse_txt_bytes(file_bytes: bytes) -> list[dict[str, Any]]:
    """
    Mem-parse konten TXT dari bytes (upload Flask).

    Args:
        file_bytes: Konten file sebagai bytes

    Returns:
        list[dict]: List data pelanggan
    """
    try:
        content = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content = file_bytes.decode("latin-1")

    return parse_paste(content)


def parse_excel_file(file_path: str | Path) -> list[dict[str, Any]]:
    """
    Mem-parse file Excel (.xlsx / .xls).

    Kolom yang didukung (case-insensitive, lihat COLUMN_ALIASES):
        - Nomor IndiHome (wajib)
        - Nomor WA (wajib)
        - Nama, Segment, Tagihan (opsional)
        - Kolom tambahan apapun

    Args:
        file_path: Path ke file Excel

    Returns:
        list[dict]: List data pelanggan

    Raises:
        ValueError: Jika kolom wajib tidak ditemukan
    """
    log.info(f"parse_excel_file: membaca '{file_path}'")
    df = pd.read_excel(file_path, dtype=str)
    return _process_dataframe(df)


def parse_excel_bytes(file_bytes: bytes) -> list[dict[str, Any]]:
    """
    Mem-parse konten Excel dari bytes (upload Flask).

    Args:
        file_bytes: Konten file sebagai bytes

    Returns:
        list[dict]: List data pelanggan
    """
    df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
    return _process_dataframe(df)


def _process_dataframe(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Memproses DataFrame pandas menjadi List[dict].

    Args:
        df: DataFrame hasil baca Excel

    Returns:
        list[dict]: List data pelanggan yang sudah dinormalisasi
    """
    # Hapus baris yang semua kolomnya kosong
    df = df.dropna(how="all")
    df = df.reset_index(drop=True)

    # Normalisasi nama kolom
    df.columns = [_normalize_column(str(c)) for c in df.columns]

    # Validasi kolom wajib
    required_cols = ["nomor_indihome", "nomor_wa"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"Kolom wajib tidak ditemukan di Excel: {missing}. "
            f"Kolom yang tersedia: {list(df.columns)}"
        )

    customers: list[dict] = []

    for row_num, (_, row) in enumerate(df.iterrows(), start=2):
        nomor_indihome = str(row.get("nomor_indihome", "")).strip()
        nomor_wa       = _format_phone(str(row.get("nomor_wa", "")).strip())

        # Skip baris kosong
        if not nomor_indihome or not nomor_wa or nomor_wa in ("", "nan"):
            log.debug(f"Skip baris {row_num}: data kosong")
            continue

        # Buat dict dari seluruh kolom
        customer: dict[str, Any] = {
            "nomor_indihome": nomor_indihome,
            "nomor_wa"      : nomor_wa,
            "nama"          : _safe_str(row.get("nama", "")),
            "segment"       : _safe_str(row.get("segment", "")),
            "tagihan"       : _safe_str(row.get("tagihan", "")),
            "_row"          : row_num,
        }

        # Tambahkan kolom tambahan yang mungkin ada
        for col in df.columns:
            if col not in customer:
                customer[col] = _safe_str(row.get(col, ""))

        customers.append(customer)

    log.info(f"parse_excel: {len(customers)} pelanggan dari {len(df)} baris")
    return customers


def _format_phone(phone: str) -> str:
    """
    Memformat nomor telepon ke format internasional Indonesia.

    Contoh:
        '08123456789'   → '628123456789'
        '8123456789'    → '628123456789'
        '628123456789'  → '628123456789'
        '+628123456789' → '628123456789'

    Args:
        phone: Nomor telepon mentah

    Returns:
        str: Nomor dalam format internasional (diawali 62)
    """
    phone = str(phone).strip()

    # Hapus karakter non-digit
    import re
    phone = re.sub(r"\D", "", phone)

    if not phone:
        return phone

    if phone.startswith("62"):
        return phone
    elif phone.startswith("0"):
        return "62" + phone[1:]
    elif phone.startswith("8"):
        return "62" + phone
    else:
        return phone


def _safe_str(value: Any) -> str:
    """Konversi nilai ke string, mengganti 'nan' dengan string kosong."""
    s = str(value).strip()
    return "" if s.lower() == "nan" else s


def get_sample_data(customers: list[dict]) -> dict[str, Any]:
    """
    Mengambil data pelanggan pertama sebagai sampel untuk preview template.

    Args:
        customers: List data pelanggan

    Returns:
        dict: Data pelanggan pertama, atau dict kosong jika tidak ada
    """
    if not customers:
        return {
            "nomor_indihome": "122874260591",
            "nomor_wa"      : "6285797452721",
            "nama"          : "Contoh Pelanggan",
            "segment"       : "IndiHome",
            "tagihan"       : "350.000",
        }
    return customers[0]

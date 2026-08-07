"""
placeholder.py — Template Placeholder Module
=============================================
Mengganti semua placeholder dalam template pesan
dengan data pelanggan yang sebenarnya.

Placeholder yang didukung:
    {nomor_indihome}, {nama}, {nomor}, {segment},
    {tagihan}, dan kolom lain dari Excel/TXT.

Author  : CRM Team - PT Telkomsel Branch Karawang
Project : CRM Blast IndiHome
"""

from __future__ import annotations

import re
from typing import Any

from logger import log


# ──────────────────────────────────────────────
# Konstanta placeholder standar
# ──────────────────────────────────────────────
STANDARD_PLACEHOLDERS: list[str] = [
    "nomor_indihome",
    "nama",
    "nomor",
    "segment",
    "tagihan",
]


def extract_placeholders(template: str) -> list[str]:
    """
    Mengekstrak semua placeholder dari template pesan.

    Args:
        template: String template yang berisi placeholder {key}

    Returns:
        list[str]: Daftar nama placeholder yang ditemukan

    Example:
        >>> extract_placeholders("Halo {nama}, tagihan Anda {tagihan}")
        ['nama', 'tagihan']
    """
    return re.findall(r"\{(\w+)\}", template)


def replace_placeholders(template: str, data: dict[str, Any]) -> tuple[str, list[str]]:
    """
    Mengganti semua placeholder dalam template dengan nilai dari data pelanggan.

    Args:
        template : String template dengan placeholder {key}
        data     : Dict berisi data pelanggan {key: value}

    Returns:
        tuple[str, list[str]]:
            - Pesan hasil substitusi
            - Daftar placeholder yang tidak ditemukan (warnings)

    Example:
        >>> tpl = "Halo {nama}, nomor IndiHome Anda: {nomor_indihome}"
        >>> data = {"nama": "Budi", "nomor_indihome": "122874260591"}
        >>> msg, warns = replace_placeholders(tpl, data)
        >>> print(msg)
        "Halo Budi, nomor IndiHome Anda: 122874260591"
    """
    placeholders = extract_placeholders(template)
    warnings: list[str] = []
    result = template

    for key in placeholders:
        # Normalisasi key: lowercase, strip whitespace
        normalized_key = key.strip().lower()

        # Cari di data (case-insensitive)
        value = _find_value(data, normalized_key)

        if value is not None:
            result = result.replace(f"{{{key}}}", str(value))
            log.debug(f"Placeholder {{{key}}} → '{value}'")
        else:
            # Placeholder tidak ditemukan — biarkan kosong dan beri warning
            result = result.replace(f"{{{key}}}", f"[{key}?]")
            warnings.append(key)
            log.warning(f"Placeholder {{{key}}} tidak ditemukan dalam data pelanggan")

    return result, warnings


def _find_value(data: dict[str, Any], key: str) -> Any | None:
    """
    Mencari nilai dari dict data secara case-insensitive.

    Args:
        data : Dict data pelanggan
        key  : Key yang dicari (lowercase)

    Returns:
        Any | None: Nilai yang ditemukan, atau None jika tidak ada
    """
    # Exact match terlebih dahulu
    if key in data:
        return data[key]

    # Case-insensitive match
    for k, v in data.items():
        if str(k).strip().lower() == key:
            return v

    # Alias mapping untuk kolom umum
    aliases: dict[str, list[str]] = {
        "nomor_indihome": ["no_indihome", "nomorindihome", "no indihome", "id_pelanggan", "id pelanggan"],
        "nomor"         : ["nomor_wa", "no_wa", "phone", "phone_number", "nowa", "wa"],
        "nama"          : ["name", "customer_name", "nama_pelanggan"],
        "segment"       : ["segmen", "seg"],
        "tagihan"       : ["bill", "billing", "total_tagihan"],
    }

    if key in aliases:
        for alias in aliases[key]:
            for k, v in data.items():
                if str(k).strip().lower() == alias:
                    return v

    return None


def validate_template(template: str, sample_data: dict[str, Any]) -> dict[str, Any]:
    """
    Memvalidasi template dengan data sampel dan memberikan laporan.

    Args:
        template    : String template pesan
        sample_data : Contoh data pelanggan untuk preview

    Returns:
        dict: {
            'preview'  : str  — hasil substitusi,
            'warnings' : list — placeholder yang tidak ditemukan,
            'found'    : list — placeholder yang berhasil diganti,
            'valid'    : bool — True jika tidak ada warning
        }
    """
    placeholders = extract_placeholders(template)
    preview, warnings = replace_placeholders(template, sample_data)
    found = [p for p in placeholders if p not in warnings]

    return {
        "preview" : preview,
        "warnings": warnings,
        "found"   : found,
        "valid"   : len(warnings) == 0,
    }

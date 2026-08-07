# CRM Blast IndiHome
### PT Telkomsel Branch Karawang — Internship Project

Aplikasi dashboard CRM untuk mengirim pesan WhatsApp secara otomatis kepada pelanggan IndiHome menggunakan **Python Flask + Selenium + Bootstrap 5**.

> **Note:** Aplikasi ini digunakan untuk komunikasi resmi kepada pelanggan yang telah menjadi database perusahaan. Bukan untuk spam.

---

## Cara Menjalankan

### 1. Install Dependencies
```bash
cd crm_blast
pip install -r requirements.txt
```

### 2. Jalankan Aplikasi
```bash
python app.py
```

### 3. Buka Browser
```
http://127.0.0.1:5000
```

---

## Cara Pakai

### Langkah 1 — Input Data Pelanggan
Pilih salah satu metode:
- **Paste**: Tempel langsung format `NomorIndiHome NomorWA` per baris
- **Upload TXT**: Upload file `.txt` dengan format yang sama
- **Upload Excel**: Upload file `.xlsx` dengan kolom Nomor IndiHome, Nomor WA, Nama, dll.

### Langkah 2 — Isi Template Pesan
Gunakan placeholder berikut:
- `{nomor_indihome}` — Nomor IndiHome pelanggan
- `{nama}` — Nama pelanggan
- `{nomor}` — Nomor WA pelanggan
- `{segment}` — Segment layanan
- `{tagihan}` — Nominal tagihan

Klik **Preview** untuk melihat hasil sebelum blast.

### Langkah 3 — Upload Gambar (Opsional)
Upload gambar promo JPG/PNG/WEBP. Gambar akan dikirim setelah pesan teks.

### Langkah 4 — Pengaturan
- **Delay antar nomor**: 5–60 detik (default 5–10)
- **Max retry**: 1–5 kali (default 3)
- **Delay gambar**: delay antar upload gambar

### Langkah 5 — Mulai Blast
Klik **Mulai Blast**. Chrome akan terbuka dan WhatsApp Web akan dimuat.
- Scan QR jika baru pertama kali (selanjutnya tidak perlu karena menggunakan Chrome Profile)
- Monitor progress di dashboard realtime

### Stop & Resume
- Klik **Stop** untuk menghentikan blast sementara
- Klik **Resume** untuk melanjutkan dari posisi terakhir

### Export Laporan
Klik **Export Excel** untuk download laporan hasil blast.

---

## Struktur Folder

```
crm_blast/
├── app.py              # Flask server (entry point)
├── config.py           # Konfigurasi global
├── wa.py               # WhatsAppBlast class (Selenium)
├── blast_engine.py     # Engine blast + threading
├── data_parser.py      # Parser input data
├── placeholder.py      # Substitusi template
├── report.py           # Export Excel
├── logger.py           # Logging terpusat
├── templates/
│   └── index.html      # Dashboard UI
├── static/
│   ├── css/style.css   # Custom CSS (Telkomsel theme)
│   └── js/app.js       # Frontend JavaScript
├── uploads/            # Gambar yang diupload
├── reports/            # Laporan Excel output
├── logs/blast.log      # Log aktivitas
├── data/blast_state.json  # State untuk resume
└── chrome_profile/     # Chrome persistent profile
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, Flask 3.x |
| Automation | Selenium 4.x, webdriver-manager |
| Data | Pandas, OpenPyXL |
| Frontend | Bootstrap 5, JavaScript, SSE |
| Storage | JSON state, Excel report |

---

## Catatan Penting

- Chrome hanya dibuka **SATU KALI** selama sesi blast
- Gunakan Chrome Profile agar tidak perlu scan QR berulang
- Seluruh error dicatat di `logs/blast.log`
- State disimpan di `data/blast_state.json` untuk fitur resume

---

*Dibuat oleh Tim CRM — PT Telkomsel Branch Karawang*

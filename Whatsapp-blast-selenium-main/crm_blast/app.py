"""
app.py — Flask Application Entry Point
=========================================
REST API dan SSE endpoint untuk CRM Blast IndiHome.
Mengelola semua request dari frontend dashboard.

API Endpoints:
    GET  /                    → Dashboard HTML
    POST /api/start           → Mulai blast
    POST /api/stop            → Stop blast
    POST /api/resume          → Resume blast
    GET  /api/status          → Status blast realtime
    GET  /api/logs            → SSE stream log
    POST /api/upload-data     → Upload data pelanggan (TXT/Excel)
    POST /api/upload-image    → Upload gambar promo
    GET  /api/export          → Download laporan Excel
    GET  /api/preview-template → Preview template pesan

Author  : CRM Team - PT Telkomsel Branch Karawang
Project : CRM Blast IndiHome
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_file,
    stream_with_context,
)

from blast_engine import engine
from config import (
    ALLOWED_DATA_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    DEFAULT_DELAY_MAX,
    DEFAULT_DELAY_MIN,
    DEFAULT_RETRY_MAX,
    DEFAULT_TEMPLATE,
    FLASK_DEBUG,
    FLASK_HOST,
    FLASK_PORT,
    FLASK_SECRET_KEY,
    MAX_CONTENT_LENGTH,
    REPORT_FILE,
    UPLOAD_FOLDER,
)
from data_parser import (
    get_sample_data,
    parse_excel_bytes,
    parse_paste,
    parse_txt_bytes,
)
from logger import log
from placeholder import validate_template
from report import generate_report


# ──────────────────────────────────────────────
# Flask App Setup
# ──────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# Uploaded gambar yang tersimpan (path list)
_uploaded_images: list[str] = []


# ──────────────────────────────────────────────
# ROUTES — Pages
# ──────────────────────────────────────────────

@app.route("/")
def index():
    """Dashboard utama."""
    saved_state = engine.load_saved_state()
    has_resume = (
        saved_state is not None
        and saved_state.get("status") in ("STOPPED", "RUNNING")
        and saved_state.get("current_index", 0) > 0
    )
    return render_template(
        "index.html",
        default_template=DEFAULT_TEMPLATE,
        has_resume=has_resume,
        saved_state=saved_state,
    )


# ──────────────────────────────────────────────
# ROUTES — Blast Control
# ──────────────────────────────────────────────

@app.route("/api/start", methods=["POST"])
def api_start():
    """
    Memulai blast WhatsApp.

    Request JSON:
        {
            "input_type": "paste" | "data",
            "paste_text": "...",     # jika paste
            "template"  : "...",
            "settings"  : {
                "delay_min" : 5,
                "delay_max" : 10,
                "retry_max" : 3,
                "img_delay" : 2.0,
            }
        }
    """
    try:
        data = request.get_json(force=True)

        # ── Ambil data pelanggan ────────────────────────────
        input_type = data.get("input_type", "paste")
        customers  = []

        if input_type == "paste":
            paste_text = data.get("paste_text", "").strip()
            if not paste_text:
                return jsonify({"ok": False, "message": "Teks paste kosong."}), 400
            customers = parse_paste(paste_text)

        elif input_type == "data":
            # Gunakan data yang sudah di-upload sebelumnya
            customers = engine.get_customers()

        if not customers:
            return jsonify({"ok": False, "message": "Data pelanggan kosong."}), 400

        # ── Ambil template ──────────────────────────────────
        template = data.get("template", DEFAULT_TEMPLATE).strip()
        if not template:
            return jsonify({"ok": False, "message": "Template pesan kosong."}), 400

        # ── Ambil settings ──────────────────────────────────
        settings_raw = data.get("settings", {})
        settings = {
            "delay_min": int(settings_raw.get("delay_min", DEFAULT_DELAY_MIN)),
            "delay_max": int(settings_raw.get("delay_max", DEFAULT_DELAY_MAX)),
            "retry_max": int(settings_raw.get("retry_max", DEFAULT_RETRY_MAX)),
            "img_delay": float(settings_raw.get("img_delay", 2.0)),
        }

        # ── Simpan ke engine ────────────────────────────────
        engine.set_customers(customers)
        engine.set_template(template)
        engine.set_images(_uploaded_images.copy())

        # ── Mulai blast ─────────────────────────────────────
        ok = engine.start(customers, template, _uploaded_images.copy(), settings)

        if ok:
            log.info(f"Blast dimulai: {len(customers)} pelanggan")
            return jsonify({
                "ok"     : True,
                "message": f"Blast dimulai untuk {len(customers)} pelanggan.",
                "total"  : len(customers),
            })
        else:
            return jsonify({"ok": False, "message": "Blast sudah berjalan."}), 409

    except Exception as e:
        log.error(f"Error /api/start: {e}", exc_info=True)
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """Menghentikan blast yang sedang berjalan."""
    ok = engine.stop()
    if ok:
        return jsonify({"ok": True, "message": "Stop signal dikirim."})
    return jsonify({"ok": False, "message": "Blast tidak sedang berjalan."}), 400


@app.route("/api/resume", methods=["POST"])
def api_resume():
    """Melanjutkan blast dari state tersimpan."""
    # Jika ada data baru dari request, set ke engine
    data = request.get_json(force=True, silent=True) or {}
    template = data.get("template", "")
    if template:
        engine.set_template(template)
    if _uploaded_images:
        engine.set_images(_uploaded_images.copy())

    ok = engine.resume()
    if ok:
        return jsonify({"ok": True, "message": "Blast dilanjutkan."})
    return jsonify({"ok": False, "message": "Tidak ada state tersimpan atau blast sudah berjalan."}), 400


# ──────────────────────────────────────────────
# ROUTES — Status & SSE
# ──────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    """
    Mengembalikan status blast terkini untuk polling frontend.

    Response JSON:
        {
            "status"  : "RUNNING" | "IDLE" | "DONE" | "STOPPED",
            "total"   : int,
            "success" : int,
            "failed"  : int,
            "skipped" : int,
            "progress": float,
            "current_index": int,
            "results" : [...],
        }
    """
    status = engine.get_status()
    # Tambah info resume
    saved = engine.load_saved_state()
    status["has_resume"] = (
        saved is not None
        and saved.get("status") in ("STOPPED", "RUNNING")
        and saved.get("current_index", 0) > 0
    )
    return jsonify(status)


@app.route("/api/logs")
def api_logs():
    """
    Server-Sent Events stream untuk log realtime.
    Frontend terhubung sekali, menerima event terus-menerus.
    """
    def event_stream():
        log_queue = engine.get_log_queue()
        while True:
            try:
                # Timeout 1 detik agar connection tetap hidup
                item = log_queue.get(timeout=1)
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            except Exception:
                # Kirim heartbeat agar connection tidak timeout
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control"  : "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ──────────────────────────────────────────────
# ROUTES — Upload
# ──────────────────────────────────────────────

@app.route("/api/upload-data", methods=["POST"])
def api_upload_data():
    """
    Upload data pelanggan (TXT atau Excel).

    Form data:
        file     : File TXT atau Excel
        method   : 'txt' | 'excel'

    Response JSON:
        {
            "ok"      : bool,
            "count"   : int,
            "preview" : list[dict] (5 data pertama),
            "columns" : list[str],
        }
    """
    try:
        if "file" not in request.files:
            return jsonify({"ok": False, "message": "File tidak ditemukan."}), 400

        file = request.files["file"]
        if not file.filename:
            return jsonify({"ok": False, "message": "Nama file kosong."}), 400

        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_DATA_EXTENSIONS:
            return jsonify({
                "ok"     : False,
                "message": f"Format tidak didukung: {ext}. Gunakan TXT atau Excel."
            }), 400

        file_bytes = file.read()

        # Parse sesuai tipe
        if ext == ".txt":
            customers = parse_txt_bytes(file_bytes)
        else:
            customers = parse_excel_bytes(file_bytes)

        if not customers:
            return jsonify({"ok": False, "message": "File kosong atau tidak ada data valid."}), 400

        # Simpan ke engine
        engine.set_customers(customers)

        log.info(f"Data diupload: {len(customers)} pelanggan dari '{file.filename}'")

        return jsonify({
            "ok"     : True,
            "count"  : len(customers),
            "preview": customers[:5],
            "columns": list(customers[0].keys()) if customers else [],
            "message": f"{len(customers)} pelanggan berhasil dimuat.",
        })

    except ValueError as e:
        log.error(f"Validation error upload data: {e}")
        return jsonify({"ok": False, "message": str(e)}), 400
    except Exception as e:
        log.error(f"Error upload data: {e}", exc_info=True)
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route("/api/upload-image", methods=["POST"])
def api_upload_image():
    """
    Upload satu atau lebih gambar promo.

    Form data:
        files[] : Multiple image files

    Response JSON:
        {
            "ok"    : bool,
            "files" : list[str] — nama file yang diupload,
            "paths" : list[str] — path absolut
        }
    """
    global _uploaded_images

    try:
        files = request.files.getlist("files[]")
        if not files:
            files = request.files.getlist("file")  # fallback

        if not files or not files[0].filename:
            # Jika clear request (no files)
            _uploaded_images = []
            return jsonify({"ok": True, "files": [], "paths": [], "message": "Gambar dihapus."})

        saved_files = []
        saved_paths = []

        for file in files:
            if not file.filename:
                continue

            ext = Path(file.filename).suffix.lower()
            if ext not in ALLOWED_IMAGE_EXTENSIONS:
                log.warning(f"Tipe gambar tidak didukung: {file.filename}")
                continue

            # Buat nama unik agar tidak bentrok
            unique_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
            save_path   = UPLOAD_FOLDER / unique_name
            file.save(str(save_path))

            saved_files.append(unique_name)
            saved_paths.append(str(save_path.resolve()))
            log.info(f"Gambar diupload: {unique_name}")

        _uploaded_images = saved_paths
        engine.set_images(saved_paths)

        return jsonify({
            "ok"    : True,
            "files" : saved_files,
            "paths" : saved_paths,
            "count" : len(saved_paths),
            "message": f"{len(saved_paths)} gambar berhasil diupload.",
        })

    except Exception as e:
        log.error(f"Error upload gambar: {e}", exc_info=True)
        return jsonify({"ok": False, "message": str(e)}), 500


# ──────────────────────────────────────────────
# ROUTES — Export & Template
# ──────────────────────────────────────────────

@app.route("/api/export")
def api_export():
    """Download laporan Excel hasil blast."""
    try:
        results = engine.get_results()
        if not results:
            return jsonify({"ok": False, "message": "Belum ada hasil blast."}), 400

        report_path = generate_report(results)

        return send_file(
            str(report_path),
            as_attachment=True,
            download_name=f"laporan_blast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except Exception as e:
        log.error(f"Error export: {e}", exc_info=True)
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route("/api/preview-template", methods=["POST"])
def api_preview_template():
    """
    Preview template dengan data sampel.

    Request JSON:
        {
            "template": "Halo {nama}...",
            "sample"  : {"nama": "Budi", ...}  # opsional
        }

    Response JSON:
        {
            "preview" : str,
            "warnings": list[str],
            "valid"   : bool
        }
    """
    try:
        data     = request.get_json(force=True)
        template = data.get("template", DEFAULT_TEMPLATE)
        sample   = data.get("sample")

        if not sample:
            customers = engine.get_customers()
            sample    = get_sample_data(customers)

        result = validate_template(template, sample)
        return jsonify(result)

    except Exception as e:
        log.error(f"Error preview template: {e}")
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route("/api/clear-images", methods=["POST"])
def api_clear_images():
    """Menghapus semua gambar yang sudah diupload."""
    global _uploaded_images
    _uploaded_images = []
    engine.set_images([])
    return jsonify({"ok": True, "message": "Gambar dihapus."})


# ──────────────────────────────────────────────
# Error Handlers
# ──────────────────────────────────────────────

@app.errorhandler(413)
def too_large(e):
    return jsonify({"ok": False, "message": "File terlalu besar (max 50MB)."}), 413


@app.errorhandler(404)
def not_found(e):
    return jsonify({"ok": False, "message": "Endpoint tidak ditemukan."}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"ok": False, "message": "Internal server error."}), 500


# ──────────────────────────────────────────────
# QR Code Endpoint (untuk cloud deployment)
# Digunakan saat pertama kali deploy di Railway,
# agar admin bisa scan QR WhatsApp dari browser.
# ──────────────────────────────────────────────

@app.route("/api/qr-screenshot", methods=["GET"])
def qr_screenshot():
    """
    Ambil screenshot Chrome saat ini sebagai base64.
    Digunakan untuk scan QR WhatsApp Web di cloud.
    GET /api/qr-screenshot
    """
    try:
        blast = engine._blast
        if not blast or not blast.driver:
            return jsonify({
                "ok": False,
                "message": "Browser belum aktif. Mulai blast terlebih dahulu untuk membuka Chrome.",
                "screenshot": None
            }), 200

        screenshot_b64 = blast.driver.get_screenshot_as_base64()
        return jsonify({
            "ok": True,
            "screenshot": screenshot_b64,
            "message": "Screenshot berhasil diambil."
        })
    except Exception as e:
        log.error(f"[QR_SCREENSHOT] Error: {e}")
        return jsonify({"ok": False, "message": str(e), "screenshot": None}), 500




# ──────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("  CRM Blast IndiHome — PT Telkomsel Branch Karawang")
    log.info(f"  Server: http://{FLASK_HOST}:{FLASK_PORT}")
    log.info("=" * 60)

    app.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=FLASK_DEBUG,
        threaded=True,
        use_reloader=False,  # Nonaktifkan reloader agar driver tidak double
    )

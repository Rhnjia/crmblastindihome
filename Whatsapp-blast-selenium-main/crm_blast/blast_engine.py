"""
blast_engine.py — Blast Engine (Background Thread)
====================================================
Mengatur logika loop blast, threading, state management,
retry, stop/resume, dan callback ke Flask via SSE queue.

Author  : CRM Team - PT Telkomsel Branch Karawang
Project : CRM Blast IndiHome
"""

from __future__ import annotations

import json
import queue
import threading
import time
import traceback
from datetime import datetime
from typing import Any, Callable, Optional

from config import (
    DEFAULT_DELAY_MAX,
    DEFAULT_DELAY_MIN,
    DEFAULT_RETRY_MAX,
    RESULT_FAILED,
    RESULT_SKIPPED,
    RESULT_SUCCESS,
    STATE_FILE,
    STATUS_DONE,
    STATUS_IDLE,
    STATUS_RUNNING,
    STATUS_STOPPED,
)
from logger import log
from placeholder import replace_placeholders
from wa import WhatsAppBlast


class BlastEngine:
    """
    Engine utama untuk menjalankan blast WhatsApp secara background.

    Menggunakan threading agar Flask tidak freeze.
    Menyimpan state ke JSON untuk fitur resume.
    Mengirim log realtime ke SSE via queue.

    Attributes:
        _blast       : Instance WhatsAppBlast
        _thread      : Background thread blast
        _stop_event  : Event untuk menghentikan blast
        _state       : Dict state blast saat ini
        _log_queue   : Queue untuk SSE log events
        _customers   : List data pelanggan
        _template    : Template pesan
        _images      : List path gambar
        _settings    : Dict pengaturan blast

    Example:
        >>> engine = BlastEngine()
        >>> engine.start(customers, template, images, settings)
        >>> engine.stop()
        >>> engine.resume()
    """

    def __init__(self) -> None:
        self._blast: Optional[WhatsAppBlast] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._log_queue: queue.Queue = queue.Queue(maxsize=1000)
        self._lock = threading.Lock()

        # State blast
        self._state: dict[str, Any] = {
            "status"       : STATUS_IDLE,
            "current_index": 0,
            "total"        : 0,
            "success"      : 0,
            "failed"       : 0,
            "skipped"      : 0,
            "start_time"   : None,
            "end_time"     : None,
            "results"      : [],  # List hasil per pelanggan
        }

        # Data blast
        self._customers: list[dict] = []
        self._template: str = ""
        self._images: list[str] = []
        self._settings: dict[str, Any] = {}

    # ──────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────

    def start(
        self,
        customers: list[dict],
        template: str,
        images: list[str],
        settings: Optional[dict] = None,
    ) -> bool:
        """
        Memulai blast dari awal.

        Args:
            customers : List data pelanggan [{nomor_wa, nomor_indihome, ...}]
            template  : Template pesan dengan placeholder
            images    : List path absolut gambar
            settings  : Dict pengaturan {delay_min, delay_max, retry_max, ...}

        Returns:
            bool: True jika blast berhasil dimulai
        """
        if self.is_running():
            self._log("Blast sedang berjalan, tidak dapat memulai lagi.", "warning")
            return False

        self._customers = customers
        self._template  = template
        self._images    = images
        self._settings  = settings or {}
        self._stop_event.clear()

        # Reset state (Belum RUNNING)
        self._state.update({
            "status"       : STATUS_IDLE,
            "current_index": 0,
            "total"        : len(customers),
            "success"      : 0,
            "failed"       : 0,
            "skipped"      : 0,
            "start_time"   : datetime.now().isoformat(),
            "end_time"     : None,
            "results"      : [],
        })

        # Inisialisasi WhatsAppBlast
        if not self._init_blast_instance():
            self._log("Gagal inisialisasi driver. Blast dibatalkan.", "error")
            log.error("[ENGINE] Inisialisasi ChromeDriver / WhatsApp gagal.")
            return False

        # Driver siap -> ubah status menjadi RUNNING
        self._state["status"] = STATUS_RUNNING

        # Jalankan di background thread
        self._thread = threading.Thread(
            target=self._blast_loop,
            name="BlastThread",
            daemon=True,
        )
        self._thread.start()
        log.info("[MILESTONE] Blast Thread Started")
        log.info(f"Blast dimulai: {len(customers)} pelanggan")
        return True

    def stop(self) -> bool:
        """
        Menghentikan blast dengan aman.
        State disimpan untuk keperluan resume.

        Returns:
            bool: True jika stop signal berhasil dikirim
        """
        if not self.is_running():
            return False

        self._log("Stop signal dikirim. Menunggu nomor saat ini selesai...", "warning")
        self._stop_event.set()
        self._state["status"] = STATUS_STOPPED
        self._save_state()
        return True

    def resume(self) -> bool:
        """
        Melanjutkan blast dari state tersimpan.

        Returns:
            bool: True jika resume berhasil
        """
        if self.is_running():
            self._log("Blast sedang berjalan.", "warning")
            return False

        saved = self._load_state()
        if not saved:
            self._log("Tidak ada state tersimpan untuk di-resume.", "error")
            return False

        if not self._customers:
            self._log("Data pelanggan tidak tersedia. Mohon upload data terlebih dahulu.", "error")
            return False

        # Restore state dari file
        self._state.update(saved)
        self._state["status"] = STATUS_RUNNING
        self._stop_event.clear()

        self._log(
            f"Melanjutkan blast dari index {self._state['current_index']} "
            f"/ {self._state['total']}",
            "info"
        )

        # Re-init blast instance
        self._init_blast_instance()

        self._thread = threading.Thread(
            target=self._blast_loop,
            name="BlastThread-Resume",
            daemon=True,
        )
        self._thread.start()
        return True

    def get_status(self) -> dict[str, Any]:
        """
        Mendapatkan status blast saat ini untuk polling API.

        Returns:
            dict: Status lengkap blast
        """
        with self._lock:
            state = self._state.copy()
            # Hitung progress percentage
            total = state.get("total", 0)
            done  = state.get("success", 0) + state.get("failed", 0) + state.get("skipped", 0)
            state["progress"] = round((done / total * 100) if total > 0 else 0, 1)
            return state

    def is_running(self) -> bool:
        """Memeriksa apakah blast sedang berjalan."""
        return (
            self._thread is not None
            and self._thread.is_alive()
            and self._state["status"] == STATUS_RUNNING
        )

    def get_log_queue(self) -> queue.Queue:
        """Mengembalikan queue log untuk SSE streaming."""
        return self._log_queue

    def get_customers(self) -> list[dict]:
        """Mengembalikan data pelanggan."""
        return self._customers

    def set_customers(self, customers: list[dict]) -> None:
        """Set data pelanggan (digunakan sebelum resume)."""
        self._customers = customers

    def set_template(self, template: str) -> None:
        """Set template pesan."""
        self._template = template

    def set_images(self, images: list[str]) -> None:
        """Set list path gambar."""
        self._images = images

    # ──────────────────────────────────────────────────────────
    # BLAST LOOP (Background Thread)
    # ──────────────────────────────────────────────────────────

    def _blast_loop(self) -> None:
        """
        Loop utama blast yang berjalan di background thread.
        Iterasi setiap pelanggan, retry, dan simpan state.
        """
        log.info("Blast loop dimulai...")

        start_idx = self._state.get("current_index", 0)
        total     = len(self._customers)

        delay_min  = self._settings.get("delay_min",  DEFAULT_DELAY_MIN)
        delay_max  = self._settings.get("delay_max",  DEFAULT_DELAY_MAX)
        retry_max  = self._settings.get("retry_max",  DEFAULT_RETRY_MAX)

        try:
            for idx in range(start_idx, total):
                # Cek stop signal
                if self._stop_event.is_set():
                    self._log("Blast dihentikan oleh pengguna.", "warning")
                    break

                # Driver Health Check
                if self._blast and not self._blast.verify_driver():
                    self._log("Driver mati sebelum mengirim pesan. Mencoba restart...", "warning")
                    restarts = 0
                    success = False
                    while restarts < 2:
                        restarts += 1
                        if self._blast._restart_driver():
                            success = True
                            break
                    if not success:
                        self._log("Gagal me-restart driver 2 kali. Menghentikan blast.", "error")
                        log.error(f"Gagal restart driver setelah 2 kali mencoba. Menghentikan proses blast.")
                        self._state["status"] = STATUS_STOPPED
                        self._stop_event.set()
                        break

                customer = self._customers[idx]
                phone    = str(customer.get("nomor_wa", "")).strip()

                self._log(f"[{idx+1}/{total}] Memproses: {phone}", "info")

                # Update current index di state
                with self._lock:
                    self._state["current_index"] = idx

                # Generate pesan dengan placeholder substitution
                message, warnings = replace_placeholders(self._template, customer)
                if warnings:
                    self._log(f"⚠ Placeholder tidak ditemukan: {warnings}", "warning")

                # Kirim dengan retry
                result = self._send_with_retry(
                    phone=phone,
                    message=message,
                    images=self._images,
                    retry_max=retry_max,
                    customer_num=idx+1,
                    total=total,
                )

                # Simpan hasil
                self._save_result(customer, phone, result, idx+1)

                # Delay antar nomor (BUG 3: Adaptive Delays)
                if idx < total - 1 and not self._stop_event.is_set():
                    if result.get("is_invalid"):
                        # Fast delay (0.5 - 1s) untuk nomor invalid
                        self._blast.fast_delay()
                    else:
                        # Random delay (2 - 4s) untuk nomor valid
                        self._blast.random_delay()

        except Exception as e:
            log.error(f"Error tidak terduga di blast loop: {e}", exc_info=True)
            self._log(f"Error tidak terduga: {e}", "error")
        finally:
            self._on_blast_done()

    def _send_with_retry(
        self,
        phone: str,
        message: str,
        images: list[str],
        retry_max: int,
        customer_num: int,
        total: int,
    ) -> dict[str, Any]:
        """
        Mengirim pesan dengan mekanisme retry.
        Jika nomor invalid / popup terdeteksi → LANGSUNG lanjut (TIDAK RETRY).
        """
        attempts = 0
        last_result: dict = {"status": RESULT_FAILED, "reason": "Belum dicoba", "is_invalid": False}

        for attempt in range(1, retry_max + 1):
            attempts = attempt

            if self._stop_event.is_set():
                return {"status": RESULT_SKIPPED, "reason": "Dihentikan pengguna", "attempts": attempts, "is_invalid": False}

            self._log(
                f"[{customer_num}/{total}] Percobaan {attempt}/{retry_max} → {phone}",
                "info"
            )

            try:
                result = self._blast.send_to(phone, message, images)
                last_result = result
                last_result["attempts"] = attempts

                error_type = result.get("error_type", "")
                is_invalid = result.get("is_invalid", False) or error_type in ("INVALID_NUMBER", "NO_WHATSAPP", "INVALID_NUM", "NO_WA_ACCT")

                if result["status"] == RESULT_SUCCESS:
                    self._log(f"✅ [{customer_num}/{total}] SUCCESS → {phone}", "success")
                    with self._lock:
                        self._state["success"] += 1
                    return last_result

                elif is_invalid:
                    # BUG 1 & 4: Nomor tidak valid — LANGSUNG EXIT (TIDAK RETRY)
                    reason_str = result.get("reason", "INVALID_NUMBER")
                    self._log(f"⚠ [{customer_num}/{total}] {reason_str} → {phone}", "warning")
                    with self._lock:
                        self._state["failed"] += 1
                    last_result["status"] = RESULT_FAILED
                    last_result["reason"] = reason_str
                    last_result["is_invalid"] = True
                    return last_result

                else:
                    self._log(f"❌ Percobaan {attempt} gagal: {result.get('reason', '')} [{error_type}]", "error")

            except Exception as e:
                log.error(f"Exception saat send {phone} percobaan {attempt}: {e}")
                self._log(f"Error percobaan {attempt}: {e}", "error")
                last_result = {"status": RESULT_FAILED, "reason": str(e), "attempts": attempts, "is_invalid": False}

                # Cek jika browser crash
                if not self._blast.is_alive():
                    self._log("Browser crash, merestart...", "warning")
                    self._blast._restart_driver()

            # Delay antar retry
            if attempt < retry_max:
                time.sleep(1.5 * attempt)

        # Semua retry gagal
        self._log(f"❌ [{customer_num}/{total}] FAILED setelah {retry_max}x percobaan → {phone}", "error")
        with self._lock:
            self._state["failed"] += 1

        return last_result

    def _on_blast_done(self) -> None:
        """Dipanggil setelah loop blast selesai."""
        if not self._stop_event.is_set():
            self._state["status"] = STATUS_DONE
            self._log("🎉 Blast selesai!", "success")
        else:
            self._state["status"] = STATUS_STOPPED

        self._state["end_time"] = datetime.now().isoformat()
        self._save_state()

        # Kirim event done ke SSE
        self._log_queue.put({
            "type"   : "done",
            "message": "Blast selesai.",
            "level"  : "success",
        })

        log.info(
            f"Blast selesai — "
            f"Berhasil: {self._state['success']}, "
            f"Gagal: {self._state['failed']}, "
            f"Dilewati: {self._state['skipped']}"
        )

        # PASTIKAN BROWSER DITUTUP
        if self._blast:
            self._blast.close()

    # ──────────────────────────────────────────────────────────
    # STATE MANAGEMENT
    # ──────────────────────────────────────────────────────────

    def _save_state(self) -> None:
        """Menyimpan state blast ke file JSON untuk fitur resume."""
        try:
            state_to_save = {
                "current_index": self._state.get("current_index", 0),
                "total"        : self._state.get("total", 0),
                "success"      : self._state.get("success", 0),
                "failed"       : self._state.get("failed", 0),
                "skipped"      : self._state.get("skipped", 0),
                "status"       : self._state.get("status", STATUS_IDLE),
                "timestamp"    : datetime.now().isoformat(),
                "results"      : self._state.get("results", []),
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state_to_save, f, ensure_ascii=False, indent=2)
            log.debug(f"State tersimpan: index={state_to_save['current_index']}")
        except Exception as e:
            log.error(f"Gagal menyimpan state: {e}")

    def _load_state(self) -> Optional[dict]:
        """
        Memuat state blast dari file JSON.

        Returns:
            dict | None: State tersimpan, atau None jika tidak ada
        """
        try:
            if not STATE_FILE.exists():
                return None
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Gagal memuat state: {e}")
            return None

    def load_saved_state(self) -> Optional[dict]:
        """Public method untuk memuat state dari UI."""
        return self._load_state()

    # ──────────────────────────────────────────────────────────
    # RESULT TRACKING
    # ──────────────────────────────────────────────────────────

    def _save_result(
        self,
        customer: dict,
        phone: str,
        result: dict,
        num: int,
    ) -> None:
        """Menyimpan hasil pengiriman per pelanggan."""
        entry = {
            "num"           : num,
            "nomor_indihome": customer.get("nomor_indihome", ""),
            "nomor_wa"      : phone,
            "nama"          : customer.get("nama", ""),
            "status"        : result.get("status", RESULT_FAILED),
            "jam_kirim"     : datetime.now().strftime("%H:%M:%S"),
            "percobaan"     : result.get("attempts", 1),
            "keterangan"    : result.get("reason", ""),
        }

        with self._lock:
            self._state["results"].append(entry)

        # Simpan state periodik setiap 5 nomor
        if num % 5 == 0:
            self._save_state()

    def get_results(self) -> list[dict]:
        """Mendapatkan semua hasil blast."""
        with self._lock:
            return self._state.get("results", []).copy()

    # ──────────────────────────────────────────────────────────
    # INTERNAL
    # ──────────────────────────────────────────────────────────

    def _init_blast_instance(self) -> bool:
        """Inisialisasi WhatsAppBlast instance."""
        # Cleanup instance lama jika ada
        if self._blast:
            self._blast.close()

        settings = self._settings
        self._blast = WhatsAppBlast(
            delay_min    = settings.get("delay_min",   DEFAULT_DELAY_MIN),
            delay_max    = settings.get("delay_max",   DEFAULT_DELAY_MAX),
            img_delay    = settings.get("img_delay",   2.0),
            click_delay  = settings.get("click_delay", 0.5),
            log_callback = self._log,
        )
        try:
            return self._blast.start_driver()
        except Exception as e:
            log.error(f"[ENGINE] _init_blast_instance exception: {e}\n{traceback.format_exc()}")
            return False

    def _log(self, message: str, level: str = "info") -> None:
        """
        Mengirim log ke queue SSE dan Python logger.

        Args:
            message : Pesan log
            level   : 'info' | 'success' | 'warning' | 'error'
        """
        # Log ke Python logger
        log_fn = {
            "info"   : log.info,
            "success": log.info,
            "warning": log.warning,
            "error"  : log.error,
        }.get(level, log.info)
        log_fn(message)

        # Kirim ke SSE queue
        try:
            self._log_queue.put_nowait({
                "type"     : "log",
                "message"  : message,
                "level"    : level,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })
        except queue.Full:
            pass  # Queue penuh — abaikan


# ── Singleton Engine Instance ─────────────────────────────────
# Seluruh Flask routes menggunakan instance ini
engine: BlastEngine = BlastEngine()

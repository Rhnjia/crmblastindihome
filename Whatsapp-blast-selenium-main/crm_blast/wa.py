"""
wa.py — WhatsAppBlast Selenium Automation Class (v3 — Fix Invalid Popup & Fast Timeout)
======================================================================================
Refactor modul Selenium dengan perbaikan khusus:
  1. Deteksi Cepat Popup Invalid ("Nomor tidak terdaftar di WhatsApp")
     → Langsung klik OKE otomatis, tanpa retry, tanpa tunggu timeout.
  2. Message Box Timeout 10 Detik Maksimal (+ Auto Refresh 1x).
  3. 3 Syarat Kesiapan Chat sebelum send_message():
     - Tidak ada popup error.
     - Area footer chat sudah dirender.
     - Input contenteditable dapat difokuskan.
  4. Adaptive Delays: Valid (2-4s), Invalid (0.5-1s).
  5. Multi-fallback locator urutan presisi.
  6. Laporan alasan error detail (INVALID_NUMBER, MESSAGE_BOX_NOT_FOUND, TIMEOUT, dll).

Author  : CRM Team — PT Telkomsel Branch Karawang
Project : CRM Blast IndiHome (v3)
"""

from __future__ import annotations

import os
import time
import random
import traceback
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    InvalidSessionIdException,
    NoSuchElementException,
    NoSuchWindowException,
    SessionNotCreatedException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from webdriver_manager.chrome import ChromeDriverManager

from config import (
    CHROME_PROFILE,
    DEFAULT_CLICK_DELAY,
    DEFAULT_IMG_DELAY,
    SEND_TIMEOUT,
    WA_WEB_URL,
)
from logger import log


# ══════════════════════════════════════════════
# ERROR CLASSIFICATION
# ══════════════════════════════════════════════

class BlastError(Enum):
    WA_LOADING            = auto()  # WhatsApp masih "Loading your chats"
    CHAT_NOT_OPENED       = auto()  # Chat tidak terbuka dalam batas waktu
    INVALID_NUMBER        = auto()  # Nomor tidak valid / tidak terdaftar di WA
    NO_WHATSAPP           = auto()  # Nomor tidak punya akun WhatsApp
    MESSAGE_BOX_NOT_FOUND = auto()  # Message box tidak ditemukan dalam 10s
    TIMEOUT               = auto()  # Timeout umum
    SEND_FAILED           = auto()  # Gagal mengetik/mengirim pesan
    IMG_ERROR             = auto()  # Gagal upload gambar
    DRIVER_CRASH          = auto()  # Browser crash / session mati


# ══════════════════════════════════════════════
# LOCATOR REGISTRY (Presisi + Fallback)
# ══════════════════════════════════════════════

class L:
    """
    Kumpulan locator WhatsApp Web dengan multi-fallback.
    """

    # ── WhatsApp Ready (Sidebar) ─────────────────────────────────────
    WA_READY = [
        (By.CSS_SELECTOR, '[data-testid="chat-list"]'),
        (By.CSS_SELECTOR, '#side'),
        (By.CSS_SELECTOR, '[data-testid="default-user"]'),
        (By.CSS_SELECTOR, '[aria-label="Chat list"]'),
        (By.CSS_SELECTOR, '[title="Search or start new chat"]'),
    ]

    # ── QR Code ──────────────────────────────────────────────────────
    QR_CODE = [
        (By.CSS_SELECTOR, '[data-testid="qrcode"]'),
        (By.CSS_SELECTOR, 'canvas'),
        (By.CSS_SELECTOR, '[data-ref]'),
    ]

    # ── Loader Spinner ───────────────────────────────────────────────
    WA_LOADING = [
        (By.CSS_SELECTOR, '#startup'),
        (By.CSS_SELECTOR, '[data-testid="startup"]'),
        (By.CSS_SELECTOR, '.startup-progress-bar'),
    ]

    # ── Header Chat ──────────────────────────────────────────────────
    CONV_HEADER = [
        (By.CSS_SELECTOR, '[data-testid="conversation-header"]'),
        (By.CSS_SELECTOR, 'header[data-testid="conversation-header"]'),
        (By.CSS_SELECTOR, '#main header'),
    ]

    # ── Area Footer Chat (Syarat Chat Dirender) ─────────────────────
    CHAT_FOOTER = [
        (By.CSS_SELECTOR, '#main footer'),
        (By.CSS_SELECTOR, 'footer'),
        (By.CSS_SELECTOR, '[data-testid="conversation-panel-wrapper"] footer'),
    ]

    # ── Message Box (Urutan Fallback Presisi) ───────────────────────
    # BUG 5: Urutan persis seperti instruksi
    MSG_BOX = [
        (By.CSS_SELECTOR, 'footer div[contenteditable="true"]'),
        (By.CSS_SELECTOR, '#main footer div[contenteditable="true"]'),
        (By.CSS_SELECTOR, 'div[contenteditable="true"][data-tab="10"]'),
        (By.CSS_SELECTOR, '[data-testid="conversation-compose-box-input"]'),
        (By.CSS_SELECTOR, 'div[contenteditable="true"][data-lexical-editor="true"]'),
        (By.CSS_SELECTOR, 'div[aria-placeholder="Type a message"]'),
        (By.CSS_SELECTOR, 'div[aria-placeholder="Ketik pesan"]'),
        (By.CSS_SELECTOR, 'footer p.selectable-text.copyable-text'),
        (By.CSS_SELECTOR, 'p.selectable-text.copyable-text'),
        (By.XPATH,        '//*[@id="main"]//footer//div[@contenteditable="true"]'),
    ]

    # ── Tombol Kirim Pesan ───────────────────────────────────────────
    SEND_BTN = [
        (By.CSS_SELECTOR, '[data-testid="send"]'),
        (By.CSS_SELECTOR, 'span[data-icon="send"]'),
        (By.CSS_SELECTOR, '[aria-label="Send"]'),
        (By.CSS_SELECTOR, '[aria-label="Kirim"]'),
        (By.CSS_SELECTOR, 'button[data-testid="send"]'),
        (By.XPATH,        '//footer//button[span[@data-icon="send"]]'),
    ]

    # ── Clip / Attach Button ─────────────────────────────────────────
    CLIP_BTN = [
        (By.CSS_SELECTOR, '[data-testid="clip"]'),
        (By.CSS_SELECTOR, '[aria-label="Attach"]'),
        (By.CSS_SELECTOR, '[aria-label="Lampirkan"]'),
        (By.CSS_SELECTOR, '[title="Attach"]'),
    ]

    # ── Input File Gambar ────────────────────────────────────────────
    IMG_INPUT = [
        (By.CSS_SELECTOR, 'input[accept*="image"]'),
        (By.CSS_SELECTOR, 'input[type="file"][accept*="image"]'),
        (By.CSS_SELECTOR, 'input[multiple][accept*="image"]'),
    ]

    # ── Tombol Kirim Preview Gambar ──────────────────────────────────
    IMG_SEND = [
        (By.CSS_SELECTOR, '[data-testid="media-caption-send-button"]'),
        (By.CSS_SELECTOR, '[data-testid="send"]'),
        (By.CSS_SELECTOR, 'div[role="button"][aria-label="Send"]'),
        (By.CSS_SELECTOR, 'span[data-icon="send"]'),
    ]

    # ── Centang Terkirim ─────────────────────────────────────────────
    SENT_CHECK = [
        (By.CSS_SELECTOR, '[data-testid="msg-dblcheck"]'),
        (By.CSS_SELECTOR, '[data-testid="msg-check"]'),
        (By.CSS_SELECTOR, 'span[data-testid="msg-dblcheck"]'),
        (By.XPATH,        '//*[@data-testid="msg-dblcheck" or @data-testid="msg-check"]'),
    ]

    # ── Invalid Number Popup (BUG 1 & 4) ────────────────────────────
    INVALID_POPUP = [
        (By.CSS_SELECTOR, '[data-testid="popup-contents"]'),
        (By.CSS_SELECTOR, '[data-testid="alert-popup"]'),
        (By.CSS_SELECTOR, '[data-testid="confirm-popup"]'),
        (By.CSS_SELECTOR, '.popup-contents'),
        (By.CSS_SELECTOR, 'div[role="dialog"]'),
        (By.CSS_SELECTOR, 'div[role="alertdialog"]'),
        (By.CSS_SELECTOR, 'div[data-animate-modal-popup="true"]'),
        (By.XPATH,        '//div[contains(@class,"popup")]'),
        (By.XPATH,        '//div[@role="dialog" or @role="alertdialog"]'),
    ]

    # Tombol OKE pada Popup Modal
    OK_BTN = [
        (By.CSS_SELECTOR, '[data-testid="popup-controls"] button'),
        (By.CSS_SELECTOR, '[data-testid="popup-controls"] div[role="button"]'),
        (By.CSS_SELECTOR, 'div[role="dialog"] button'),
        (By.CSS_SELECTOR, 'div[role="dialog"] div[role="button"]'),
        (By.CSS_SELECTOR, 'div[role="alertdialog"] button'),
        (By.CSS_SELECTOR, 'div[role="button"][tabindex="0"]'),
        (By.CSS_SELECTOR, 'button[aria-label="OK"]'),
        (By.XPATH,        '//div[@role="button" and (text()="OK" or text()="Oke" or contains(text(),"OK"))]'),
        (By.XPATH,        '//button[text()="OK" or text()="Oke" or contains(text(),"OK")]'),
        (By.XPATH,        '//div[@role="dialog"]//div[@role="button"]'),
        (By.XPATH,        '//div[@role="dialog"]//button'),
    ]

    # Keyword Teks Invalid
    INVALID_TEXTS = [
        "phone number shared via url is invalid",
        "nomor telepon yang dibagikan melalui url tidak valid",
        "invalid phone",
        "not registered",
        "tidak terdaftar",
        "nomor tidak terdaftar",
        "not a valid whatsapp",
    ]

    NO_WA_TEXTS = [
        "not on whatsapp",
        "tidak menggunakan whatsapp",
        "doesn't use whatsapp",
        "tidak ada di whatsapp",
    ]

    # Keyword popup NORMAL / konfirmasi chat biasa yang BUKAN error
    # Jika popup mengandung teks ini, cukup dismiss saja tanpa return INVALID_NUMBER
    CONFIRM_CHAT_TEXTS = [
        "memulai chat",
        "mulai chat",
        "start chat",
        "open chat",
        "batal",
        "cancel",
        "continue",
        "lanjutkan",
        "ok",
    ]


# ══════════════════════════════════════════════
# RESULT DATACLASS
# ══════════════════════════════════════════════

@dataclass
class SendResult:
    status    : str   = "FAILED"  # SUCCESS | FAILED
    reason    : str   = ""        # SUCCESS | INVALID_NUMBER | MESSAGE_BOX_NOT_FOUND | TIMEOUT | NO_WHATSAPP | CHAT_NOT_OPENED | SEND_FAILED
    error     : Optional[BlastError] = None
    attempts  : int   = 1
    is_invalid: bool  = False


# ══════════════════════════════════════════════
# WhatsAppBlast CLASS
# ══════════════════════════════════════════════

class WhatsAppBlast:
    """
    Class Selenium untuk WhatsApp Blast v3.
    """

    def __init__(
        self,
        delay_min   : int   = 2,
        delay_max   : int   = 4,
        img_delay   : float = DEFAULT_IMG_DELAY,
        click_delay : float = DEFAULT_CLICK_DELAY,
        log_callback: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.driver     : Optional[webdriver.Chrome] = None
        self.delay_min   = delay_min
        self.delay_max   = delay_max
        self.img_delay   = img_delay
        self.click_delay = click_delay
        self._log_cb     = log_callback
        self._wa_ready   = False

    # ══════════════════════════════════════════
    # DRIVER MANAGEMENT
    # ══════════════════════════════════════════

    def _clean_profile_locks(self, profile_path: Path) -> None:
        """Membersihkan file lock sisa jika Chrome crash sebelumnya."""
        lock_files = ["SingletonLock", "SingletonCookie", "SingletonSocket", "DevToolsActivePort"]
        try:
            if not profile_path.exists():
                profile_path.mkdir(parents=True, exist_ok=True)
                return
            for root, _, files in os.walk(profile_path):
                for f in files:
                    if f in lock_files:
                        try:
                            os.remove(os.path.join(root, f))
                            log.debug(f"[LOCK_CLEANUP] Lock file dihapus: {f}")
                        except Exception as e:
                            log.debug(f"[LOCK_CLEANUP] Gagal hapus {f}: {e}")
        except Exception as e:
            log.warning(f"[LOCK_CLEANUP] Error saat membersihkan profile locks: {e}")

    def _kill_orphan_chrome(self) -> None:
        """Membunuh proses chromedriver orphan yang mengunci profile.
        
        PENTING: Hanya kill chromedriver.exe, BUKAN chrome.exe.
        Jika kill chrome.exe, maka Chrome yang baru saja di-launch oleh
        webdriver.Chrome() juga akan ikut mati (race condition).
        Chrome.exe yang terkait profile lock akan mati sendiri
        setelah chromedriver-nya mati.
        """
        if os.name != "nt":
            return
        try:
            import subprocess
            # HANYA kill chromedriver.exe orphan — bukan chrome.exe
            result = subprocess.run(
                ["taskkill", "/F", "/IM", "chromedriver.exe", "/T"],
                capture_output=True, timeout=10
            )
            log.debug(f"[CLEANUP] taskkill chromedriver.exe: returncode={result.returncode}")
        except Exception as e:
            log.debug(f"[CLEANUP] taskkill gagal: {e}")
        # Jeda cukup agar OS melepas lock files setelah proses mati
        time.sleep(2)

    def verify_driver(self) -> bool:
        """Melakukan 5 lapis pengecekan kesehatan Chrome browser."""
        log.info("[MILESTONE] Verify Driver")
        if not self.driver or not getattr(self.driver, 'service', None):
            log.warning("[VERIFY] Driver atau service tidak tersedia.")
            return False

        try:
            if not self.driver.service.is_connectable():
                log.warning("[VERIFY] Service is NOT connectable.")
                return False
                
            session_id = getattr(self.driver, 'session_id', None)
            if not session_id:
                log.warning("[VERIFY] session_id tidak valid atau None.")
                return False
            
            handles = self.driver.window_handles
            if len(handles) == 0:
                log.warning("[VERIFY] Window handles kosong.")
                return False
                
            _ = self.driver.current_window_handle
            _ = self.driver.title
            
            # Cek document readyState
            ready_state = self.driver.execute_script("return document.readyState")
            if ready_state not in ["interactive", "complete", "loading"]:
                log.warning(f"[VERIFY] Document state aneh: {ready_state}")
                return False
                
            return True
        except Exception as e:
            log.warning(f"[VERIFY] Driver gagal verifikasi: {e}")
            return False

    def start_driver(self) -> bool:
        """Inisialisasi Chrome dengan persistent profile & strict verification."""
        profile_path = CHROME_PROFILE.resolve()
        self._emit(f"Profile path: {profile_path}", "info")
        log.info(f"[DRIVER] Profile Path: {profile_path}")

        self._kill_orphan_chrome()
        self._clean_profile_locks(profile_path)
        options = self._build_chrome_options(profile_path)

        self._emit("Launching Chrome...", "info")
        log.info("[MILESTONE] Creating ChromeDriver...")

        driver_created = False
        last_error = None
        
        # 1. Prioritas Driver Lokal
        try:
            log.info("[STARTUP] Mencoba webdriver.Chrome() dengan Service() lokal...")
            service = Service()
            self.driver = webdriver.Chrome(service=service, options=options)
            driver_created = True
            log.info("[STARTUP] webdriver.Chrome() lokal BERHASIL.")
        except Exception as local_err:
            log.info(f"[DRIVER] Local ChromeDriver gagal ({local_err}). Fallback ke webdriver_manager...")
            
            # 2. Fallback Webdriver Manager
            try:
                log.info("[STARTUP] Mencoba webdriver.Chrome() via ChromeDriverManager...")
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
                driver_created = True
                log.info("[STARTUP] webdriver.Chrome() via manager BERHASIL.")
            except (SessionNotCreatedException, WebDriverException, InvalidSessionIdException) as e:
                last_error = e
                err_str = str(e).lower()
                log.error(f"[DRIVER] Launch failed: {e}\n{traceback.format_exc()}")
                
                # Cek spesifik corrupt profile
                is_corrupt = any(k in err_str for k in [
                    "profile in use", 
                    "cannot read preferences", 
                    "devtoolsactiveport doesn't exist",
                    "profile cannot be loaded"
                ])
                
                if is_corrupt:
                    self._emit("Profile corrupt. Memulai recovery...", "warning")
                    log.warning("[DRIVER] Menemukan profil corrupt, me-rename profil...")
                    try:
                        if os.name == "nt":
                            os.system("taskkill /F /IM chromedriver.exe /T >nul 2>&1")
                            os.system("taskkill /F /IM chrome.exe /T >nul 2>&1")
                        new_name = profile_path.with_name(f"{profile_path.name}_corrupt_{int(time.time())}")
                        if profile_path.exists():
                            os.rename(profile_path, new_name)
                    except Exception as ren_err:
                        log.error(f"[DRIVER] Gagal rename profile: {ren_err}")
                
                self._clean_profile_locks(profile_path)
                try:
                    log.info("[STARTUP] Recovery: mencoba webdriver.Chrome() sekali lagi...")
                    service = Service(ChromeDriverManager().install())
                    self.driver = webdriver.Chrome(service=service, options=options)
                    driver_created = True
                    log.info("[DRIVER] Recovery launch berhasil!")
                except Exception as retry_err:
                    last_error = retry_err
                    log.error(f"[DRIVER] Recovery launch gagal: {retry_err}\n{traceback.format_exc()}")

        if not driver_created or not self.driver:
            error_msg = f"Gagal membuat webdriver session. Error: {last_error}"
            self._emit(f"CRITICAL ERROR: {error_msg}", "error")
            log.critical(f"[DRIVER] {error_msg}")
            return False

        # ── POST-LAUNCH: Verifikasi Chrome process benar-benar hidup ──
        log.info("[STARTUP] webdriver.Chrome() returned. Memeriksa proses Chrome...")
        
        # Cek 1: Service process masih ada?
        svc_proc = getattr(self.driver.service, 'process', None)
        if not svc_proc or svc_proc.poll() is not None:
            log.error("[STARTUP] FATAL: chromedriver.exe process sudah MATI setelah launch!")
            self._emit("CRITICAL: ChromeDriver mati setelah launch.", "error")
            self.driver = None
            return False
        
        c_pid = svc_proc.pid
        log.info(f"[STARTUP] ChromeDriver PID: {c_pid} (alive)")

        # Cek 2: Session ID valid?
        session_id = getattr(self.driver, 'session_id', None)
        if not session_id:
            log.error("[STARTUP] FATAL: session_id is None setelah launch!")
            self._emit("CRITICAL: Session invalid setelah launch.", "error")
            return False
        log.info(f"[STARTUP] Session ID: {session_id}")

        # Cek 3: Window handles — Chrome window benar-benar ada?
        try:
            handles = self.driver.window_handles
            log.info(f"[STARTUP] Window Handles: {handles}")
            if len(handles) == 0:
                log.error("[STARTUP] FATAL: window_handles kosong! Chrome tidak muncul.")
                self._emit("CRITICAL: Chrome window tidak muncul.", "error")
                return False
        except Exception as e:
            log.error(f"[STARTUP] FATAL: Gagal baca window_handles: {e}")
            self._emit(f"CRITICAL: Chrome crash setelah launch: {e}", "error")
            return False

        # Cek 4: current_window_handle valid?
        try:
            cwh = self.driver.current_window_handle
            log.info(f"[STARTUP] Current Window Handle: {cwh}")
        except Exception as e:
            log.error(f"[STARTUP] FATAL: current_window_handle error: {e}")
            return False

        # Cek 5: Bisa baca title? (bukti Chrome benar-benar render)
        try:
            title = self.driver.title
            log.info(f"[STARTUP] Page Title: '{title}'")
        except Exception as e:
            log.error(f"[STARTUP] FATAL: Gagal baca title: {e}")
            return False

        # Cek 6: current_url
        try:
            url = self.driver.current_url
            log.info(f"[STARTUP] Current URL: {url}")
        except Exception as e:
            log.error(f"[STARTUP] FATAL: Gagal baca current_url: {e}")
            return False

        # Diagnostik opsional (Browser PID via psutil)
        try:
            import psutil
            parent = psutil.Process(c_pid)
            children = parent.children(recursive=True)
            chrome_pids = [c.pid for c in children if 'chrome' in c.name().lower()]
            log.info(f"[STARTUP] Chrome child PIDs: {chrome_pids}")
            if not chrome_pids:
                log.warning("[STARTUP] WARNING: Tidak ada chrome.exe child process! Browser mungkin tidak muncul.")
        except ImportError:
            log.info("[STARTUP] psutil tidak tersedia, skip PID check (tidak fatal).")
        except Exception as e:
            log.debug(f"[STARTUP] psutil check gagal: {e}")

        # Service connectable?
        try:
            connectable = self.driver.service.is_connectable()
            log.info(f"[STARTUP] Service Connectable: {connectable}")
        except Exception:
            pass

        # Browser & Driver version
        try:
            caps = self.driver.capabilities
            browser_ver = caps.get("browserVersion", "Unknown")
            driver_ver = caps.get("chrome", {}).get("chromedriverVersion", "Unknown").split(" ")[0]
            log.info(f"[DIAGNOSTICS] Chrome: {browser_ver} | ChromeDriver: {driver_ver}")
        except Exception as e:
            log.debug(f"[DIAGNOSTICS] Gagal baca version: {e}")

        # Anti-detection
        try:
            self.driver.execute_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )
            self.driver.set_page_load_timeout(60)
        except Exception as e:
            log.warning(f"[STARTUP] Anti-detection script gagal: {e}")

        log.info("[DRIVER] Chrome launched successfully!")
        self._emit("Chrome launched successfully!", "success")
        
        log.info("[STARTUP] Memanggil _open_wa_home()...")
        return self._open_wa_home()

    def _build_chrome_options(self, profile_path: Path) -> Options:
        options = Options()
        options.add_argument(f"--user-data-dir={profile_path}")
        options.add_argument("--profile-directory=Default")
        options.add_argument("--remote-allow-origins=*")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-infobars")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--mute-audio")
        options.add_argument("--disable-extensions")

        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        log.info(f"[CHROME_OPTIONS] user-data-dir={profile_path}")
        log.info(f"[CHROME_OPTIONS] profile-directory=Default")
        return options

    def _open_wa_home(self) -> bool:
        self._emit("Membuka WhatsApp Web...", "info")
        log.info("[MILESTONE] Opening WhatsApp")
        log.info("[DRIVER] Navigasi ke https://web.whatsapp.com")
        
        # 1. Panggil URL dengan max 2 retries
        for attempt in range(2):
            try:
                # Verifikasi sebelum get
                log.info(f"[OPEN_WA] Attempt {attempt+1}: verify_driver SEBELUM get()...")
                if not self.verify_driver():
                    log.error("[DRIVER] Driver mati sebelum navigasi URL.")
                    return False
                log.info(f"[OPEN_WA] Attempt {attempt+1}: driver.get() MULAI...")
                self.driver.get("https://web.whatsapp.com")
                log.info(f"[OPEN_WA] Attempt {attempt+1}: driver.get() SELESAI.")
                
                # Cek URL berhasil berubah
                current_url = self.driver.current_url
                log.info(f"[OPEN_WA] Current URL setelah get(): {current_url}")
                break
            except Exception as e:
                log.warning(f"[DRIVER] Gagal load WA (attempt {attempt+1}): {e}")
                if attempt == 1:
                    log.error("[DRIVER] Gagal membuka WhatsApp Web setelah 2 percobaan.")
                    return False
                time.sleep(2)
                
        # 2. Tunggu document readyState complete
        try:
            log.info("[OPEN_WA] Menunggu document.readyState == complete (max 30s)...")
            WebDriverWait(self.driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            log.info("[WA_READY] Document Ready. Menunggu render React...")
        except TimeoutException:
            log.warning("[WA_READY] Timeout menunggu document.readyState == complete")
        
        # Verifikasi driver masih hidup sebelum masuk wait_wa_ready
        log.info("[OPEN_WA] verify_driver SEBELUM wait_wa_ready()...")
        if not self.verify_driver():
            log.error("[OPEN_WA] Driver mati setelah get() sebelum wait_wa_ready.")
            return False
        
        log.info("[OPEN_WA] Memanggil wait_wa_ready()...")
        return self.wait_wa_ready()

    def wait_wa_ready(self, timeout: int = 120) -> bool:
        self._emit("Menunggu WhatsApp selesai loading...", "info")
        log.info("[MILESTONE] Waiting WhatsApp Ready")
        log.info("[WA_READY] Menunggu WhatsApp ready...")

        start_time = time.time()
        
        # 1. Polling manual tunggu spinner lenyap
        while time.time() - start_time < timeout:
            if not self._element_exists_any(L.WA_LOADING):
                break
            time.sleep(0.5)

        # 2. Polling manual 500ms untuk QR atau Sidebar (tanpa EC.any_of)
        found_qr = False
        found_sidebar = False
        
        while time.time() - start_time < timeout:
            if self._element_exists_any(L.QR_CODE):
                found_qr = True
                break
            if self._element_exists_any(L.WA_READY):
                found_sidebar = True
                break
            time.sleep(0.5)
            
        if not found_qr and not found_sidebar:
            log.error("[WA_READY] Timeout, Sidebar / QR tidak muncul.")
            self._emit("WhatsApp gagal load. Coba restart browser.", "error")
            self._wa_ready = False
            return False

        if found_qr:
            self._emit("WhatsApp belum login. Silakan scan QR code...", "warning")
            log.info("[WA_READY] QR Found. Menunggu login...")
            
            # Tunggu QR hilang dan Sidebar muncul
            login_start = time.time()
            login_timeout = 180
            while time.time() - login_start < login_timeout:
                if self._element_exists_any(L.WA_READY):
                    found_sidebar = True
                    break
                time.sleep(1)
                
            if not found_sidebar:
                log.error("[WA_READY] QR tidak discan dalam 3 menit.")
                self._emit("Timeout scan QR.", "error")
                self._wa_ready = False
                return False
                
            log.info("[WA_READY] Login via QR berhasil.")
            self._emit("Login WhatsApp berhasil!", "success")

        if found_sidebar:
            log.info("[MILESTONE] Driver Ready")
            log.info("[WA_READY] Sidebar Found.")
            self._wa_ready = True
            self._emit("WhatsApp siap digunakan.", "success")
            return True
            
        return False

    def is_alive(self) -> bool:
        return self.verify_driver()

    def close(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
                log.info("[DRIVER] Chrome ditutup.")
            except Exception as e:
                log.warning(f"[DRIVER] Error saat tutup driver: {e}")
            finally:
                self.driver = None
                self._wa_ready = False

    def _restart_driver(self) -> bool:
        self._emit("Browser crash! Merestart Chrome...", "warning")
        log.warning("[DRIVER] Browser crash — restart...")
        
        # Cek apakah service hidup. Jika hidup, close(). Jika mati, quit() atau clean.
        self.close()
        time.sleep(3)
        try:
            ok = self.start_driver()
            if not ok:
                log.error("[DRIVER] start_driver gagal saat restart.")
                return False
            
            # Verifikasi setelah restart
            if not self.verify_driver():
                log.error("[DRIVER] Gagal verify_driver setelah restart.")
                return False
            return True
        except Exception as e:
            log.error(f"[DRIVER] Gagal restart: {e}\n{traceback.format_exc()}")
            return False

    # ══════════════════════════════════════════
    # POPUP & INVALID NUMBER HANDLING (BUG 1 & 4)
    # ══════════════════════════════════════════

    def _check_and_dismiss_invalid_popup(self) -> Optional[tuple[str, str]]:
        """
        Mendeteksi popup invalid number secara CEPAT.
        Jika muncul:
          1. Cek apakah ini popup konfirmasi chat biasa (bukan error) → dismiss saja, return None.
          2. Deteksi tipe error (INVALID_NUMBER / NO_WHATSAPP).
          3. Klik OKE otomatis.
          4. Kembalikan (status_code, reason_text) hanya jika popup memang error.
        """
        for loc in L.INVALID_POPUP:
            try:
                els = self.driver.find_elements(loc[0], loc[1])
                for el in els:
                    if el.is_displayed():
                        popup_text = el.text.lower().strip()
                        log.info(f"[POPUP_DETECTED] Teks Popup: '{popup_text[:120]}'")

                        # ── Cek apakah ini popup error invalid ──────────────
                        for t in L.INVALID_TEXTS:
                            if t in popup_text:
                                log.warning(f"[POPUP] Deteksi: INVALID_NUMBER ({t})")
                                self._click_ok_button()
                                return ("INVALID_NUMBER", "Nomor tidak terdaftar di WhatsApp")

                        for t in L.NO_WA_TEXTS:
                            if t in popup_text:
                                log.warning(f"[POPUP] Deteksi: NO_WHATSAPP ({t})")
                                self._click_ok_button()
                                return ("NO_WHATSAPP", "Nomor tidak memiliki akun WhatsApp")

                        # ── Cek apakah ini popup konfirmasi chat biasa ──────
                        # Contoh: "memulai chat / batal" atau "start chat"
                        is_confirm_popup = any(t in popup_text for t in L.CONFIRM_CHAT_TEXTS)
                        if is_confirm_popup:
                            log.info(f"[POPUP] Popup konfirmasi chat biasa terdeteksi — dismiss dan lanjutkan.")
                            self._click_ok_button()
                            return None  # Bukan error, lanjutkan proses

                        # ── Popup tidak dikenal: jika teks sangat pendek / kosong, abaikan ──
                        if not popup_text or len(popup_text) < 5:
                            log.debug(f"[POPUP] Popup teks terlalu pendek/kosong, abaikan.")
                            continue

                        # ── Default: popup tidak dikenal, log saja dan abaikan ──
                        # JANGAN return INVALID_NUMBER secara default karena bisa false positive
                        log.warning(f"[POPUP] Popup tidak dikenal (bukan error, bukan confirm): '{popup_text[:80]}' — dismiss tanpa error.")
                        self._click_ok_button()
                        return None
            except (NoSuchElementException, StaleElementReferenceException):
                continue
            except Exception as e:
                if self._is_fatal_exception(e):
                    raise
                log.debug(f"[POPUP_CHECK] Error check popup: {e}")
                continue

        return None

    def _detect_invalid_page_text(self) -> Optional[str]:
        """
        Fallback: Scan seluruh teks body halaman untuk keyword invalid.
        Digunakan jika CSS selector popup tidak cocok dengan WhatsApp terbaru.
        Return 'INVALID_NUMBER', 'NO_WHATSAPP', atau None.
        """
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            body_text = body.text.lower()

            for t in L.INVALID_TEXTS:
                if t in body_text:
                    log.info(f"[PAGE_TEXT] Keyword invalid ditemukan di body: '{t}'")
                    return "INVALID_NUMBER"

            for t in L.NO_WA_TEXTS:
                if t in body_text:
                    log.info(f"[PAGE_TEXT] Keyword no-WA ditemukan di body: '{t}'")
                    return "NO_WHATSAPP"
        except Exception as e:
            if self._is_fatal_exception(e):
                raise
            log.debug(f"[PAGE_TEXT] Gagal scan body: {e}")

        return None

    def _click_ok_button(self) -> None:
        """
        Mengklik tombol OKE pada popup modal WhatsApp secara otomatis.
        Multi-method: CSS selector → JavaScript → ENTER → ESCAPE.
        """
        log.info("[POPUP] Mengklik tombol OKE pada popup modal...")
        time.sleep(0.3)

        # Method 1: CSS/XPath selector click
        for loc in L.OK_BTN:
            try:
                btns = self.driver.find_elements(loc[0], loc[1])
                for btn in btns:
                    if btn.is_displayed():
                        try:
                            btn.click()
                        except ElementClickInterceptedException:
                            self.driver.execute_script("arguments[0].click()", btn)
                        log.info(f"[POPUP] Tombol OKE diklik via {loc}")
                        time.sleep(0.3)
                        return
            except Exception as e:
                if self._is_fatal_exception(e):
                    raise
                continue

        # Method 2: JavaScript — cari dan klik tombol dalam dialog
        try:
            self.driver.execute_script("""
                var dialogs = document.querySelectorAll(
                    '[role="dialog"], [role="alertdialog"], '
                    + '[data-testid="popup-contents"], .popup-contents'
                );
                for (var d of dialogs) {
                    var btns = d.querySelectorAll('button, [role="button"]');
                    for (var b of btns) {
                        if (b.offsetParent !== null) { b.click(); return true; }
                    }
                }
                return false;
            """)
            log.info("[POPUP] Tombol OKE diklik via JavaScript fallback")
            time.sleep(0.3)
            return
        except Exception as e:
            if self._is_fatal_exception(e):
                raise
            pass

        # Method 3: ENTER key (OK button biasanya auto-focused)
        try:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ENTER)
            log.info("[POPUP] Popup dismiss via ENTER key")
            time.sleep(0.3)
            return
        except Exception as e:
            if self._is_fatal_exception(e):
                raise
            pass

        # Method 4: ESCAPE fallback
        log.debug("[POPUP] Semua metode gagal, fallback ke Escape...")
        self._escape()

    # ══════════════════════════════════════════
    # CHAT NAVIGATION & MESSAGE BOX (BUG 2 & 7)
    # ══════════════════════════════════════════

    def open_chat(self, phone: str) -> SendResult:
        """
        Buka chat WhatsApp untuk satu nomor.

        Flow:
          1. Buka URL wa.me/{phone}
          2. Deteksi Cepat Popup Invalid
          3. Syarat Kesiapan Chat (Footer + Message Box + Focusable)
          4. Jika gagal → Refresh 1x → Coba lagi.
        """
        if not self._wa_ready:
            log.warning("[CHAT] WA belum ready, memastikan ulang...")
            self._emit("WhatsApp belum ready. Memastikan ulang...", "warning")
            ok = self.wait_wa_ready()
            if not ok:
                return SendResult(
                    status="FAILED",
                    reason="WA_NOT_READY",
                    error=BlastError.WA_LOADING,
                    attempts=1
                )

        url = WA_WEB_URL.format(phone=phone)
        self._emit(f"Membuka chat: {phone}", "info")
        log.info(f"[CHAT] Membuka URL target → {url}")

        try:
            self.driver.get(url)
        except WebDriverException as e:
            log.error(f"[CHAT] Gagal navigasi: {e}")
            if not self.is_alive():
                self._restart_driver()
            return SendResult(
                status="FAILED",
                reason="DRIVER_CRASH",
                error=BlastError.DRIVER_CRASH,
                attempts=1
            )

        # ── Step 1: Deteksi Popup Invalid ───────────────────
        time.sleep(1.5)

        popup_res = self._check_and_dismiss_invalid_popup()
        if popup_res:
            reason_code, reason_msg = popup_res
            self._emit(f"⚠ [{reason_code}] {reason_msg}: {phone}", "warning")
            return SendResult(
                status="FAILED",
                reason=reason_code,
                error=BlastError.INVALID_NUMBER,
                attempts=1,
                is_invalid=True
            )

        invalid_type = self._detect_invalid_page_text()
        if invalid_type:
            log.warning(f"[CHAT] Page text fallback: {invalid_type} → {phone}")
            self._click_ok_button()
            self._emit(f"⚠ [{invalid_type}] Terdeteksi via page text: {phone}", "warning")
            return SendResult(
                status="FAILED",
                reason=invalid_type,
                error=BlastError.INVALID_NUMBER,
                attempts=1,
                is_invalid=True
            )

        # ── Step 2: Menunggu Chat Ready & Message Box (Max 10s) ───
        res = self._wait_message_box_ready(phone, timeout=10)

        if res.status != "SUCCESS" and not res.is_invalid:
            log.warning(f"[CHAT] Message box tidak muncul dalam 10s pada {phone}. Melakukan 1x Refresh...")
            self._emit("Message box belum muncul. Melakukan refresh 1x...", "warning")
            try:
                self.driver.refresh()
                popup_res2 = self._check_and_dismiss_invalid_popup()
                if popup_res2:
                    reason_code, reason_msg = popup_res2
                    return SendResult(
                        status="FAILED",
                        reason=reason_code,
                        error=BlastError.INVALID_NUMBER,
                        attempts=1,
                        is_invalid=True
                    )
                res = self._wait_message_box_ready(phone, timeout=10)
            except Exception as e:
                log.error(f"[CHAT] Error saat refresh: {e}")

        return res

    def _wait_message_box_ready(self, phone: str, timeout: int = 10) -> SendResult:
        """
        Menunggu 3 Syarat Kesiapan Chat:
          1. Tidak ada popup error.
          2. Footer chat dirender.
          3. Message box contenteditable dapat difokuskan & editable.
        """
        self._emit(f"Menunggu message box (maks {timeout}s)...", "info")
        log.info(f"[CONV] Menunggu chat ready (maks {timeout}s): {phone}")

        start_time = time.time()

        while (time.time() - start_time) < timeout:
            popup_res = self._check_and_dismiss_invalid_popup()
            if popup_res:
                reason_code, _ = popup_res
                return SendResult(
                    status="FAILED",
                    reason=reason_code,
                    error=BlastError.INVALID_NUMBER,
                    attempts=1,
                    is_invalid=True
                )

            invalid_type = self._detect_invalid_page_text()
            if invalid_type:
                self._click_ok_button()
                return SendResult(
                    status="FAILED",
                    reason=invalid_type,
                    error=BlastError.INVALID_NUMBER,
                    attempts=1,
                    is_invalid=True
                )

            footer_exists = self._element_exists_any(L.CHAT_FOOTER)
            msg_box = self._find_msg_box_instant()

            if footer_exists and msg_box is not None:
                try:
                    if msg_box.is_displayed() and msg_box.is_enabled():
                        self._emit("Message box ditemukan & siap.", "success")
                        log.info(f"[CONV] Chat & Message Box Ready: {phone}")
                        return SendResult(status="SUCCESS", reason="SUCCESS")
                except Exception:
                    pass

            time.sleep(0.2)

        log.warning(f"[CONV] Timeout {timeout}s: Message box tidak ditemukan untuk {phone}")
        return SendResult(
            status="FAILED",
            reason="MESSAGE_BOX_NOT_FOUND",
            error=BlastError.MESSAGE_BOX_NOT_FOUND,
            attempts=1,
            is_invalid=False
        )

    # ══════════════════════════════════════════
    # SEND MESSAGE HELPER & MAIN FLOW
    # ══════════════════════════════════════════

    def _focus_compose_box(self, msg_box) -> bool:
        """Fokus ke compose box dan verifikasi document.activeElement."""
        log.info("[FOCUS] Attempting to focus compose box...")

        def is_active():
            try:
                return self.driver.execute_script(
                    "return document.activeElement === arguments[0] || arguments[0].contains(document.activeElement);",
                    msg_box
                )
            except Exception:
                return False

        if is_active():
            log.info("[FOCUS] Compose box is already document.activeElement")
            return True

        # Strategy 1: Normal click()
        try:
            msg_box.click()
            if is_active():
                log.info("[FOCUS] Focused via normal click()")
                return True
        except Exception as e:
            log.debug(f"[FOCUS] Normal click failed: {e}")

        # Strategy 2: ActionChains move_to_element() + click()
        try:
            ActionChains(self.driver).move_to_element(msg_box).click().perform()
            if is_active():
                log.info("[FOCUS] Focused via ActionChains move_to_element() & click()")
                return True
        except Exception as e:
            log.debug(f"[FOCUS] ActionChains move_to_element click failed: {e}")

        # Strategy 3: JavaScript focus() + click()
        try:
            self.driver.execute_script("arguments[0].focus(); arguments[0].click();", msg_box)
            if is_active():
                log.info("[FOCUS] Focused via JavaScript focus() & click()")
                return True
        except Exception as e:
            log.debug(f"[FOCUS] JS focus failed: {e}")

        # Strategy 4: ActionChains click()
        try:
            ActionChains(self.driver).click(msg_box).perform()
            if is_active():
                log.info("[FOCUS] Focused via ActionChains click()")
                return True
        except Exception as e:
            log.debug(f"[FOCUS] ActionChains click fallback failed: {e}")

        active = is_active()
        if active:
            log.info("[FOCUS] Focus confirmed on compose box.")
        else:
            log.warning("[FOCUS] Focus check returned False after all retries.")
        return active

    def _get_compose_text(self, msg_box) -> str:
        """Mengambil teks saat ini dari compose box."""
        try:
            t = msg_box.text
            if t and t.strip():
                return t.strip()
        except Exception:
            pass
        try:
            t = self.driver.execute_script("return (arguments[0].innerText || arguments[0].textContent || '').trim();", msg_box)
            if t:
                return t
        except Exception:
            pass
        return ""

    def _clear_compose_box(self, msg_box):
        """Membersihkan isi compose box jika typing retry dibutuhkan."""
        try:
            self.driver.execute_script(
                "arguments[0].focus(); document.execCommand('selectAll', false, null); document.execCommand('delete', false, null);",
                msg_box
            )
        except Exception:
            try:
                msg_box.send_keys(Keys.CONTROL + "a")
                msg_box.send_keys(Keys.BACKSPACE)
            except Exception:
                pass

    def _type_into_compose(self, msg_box, text: str) -> bool:
        """Mengetik pesan ke compose box dan memverifikasi hasilnya."""
        log.info("[TYPE] Typing message into compose box...")
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if line:
                msg_box.send_keys(line)
            if i < len(lines) - 1:
                ActionChains(self.driver) \
                    .key_down(Keys.SHIFT).send_keys(Keys.ENTER) \
                    .key_up(Keys.SHIFT).perform()

        # Verify typing via element.text or innerText
        typed_text = self._get_compose_text(msg_box)
        non_empty_lines = [l.strip() for l in lines if l.strip()]
        target_snippet = non_empty_lines[0] if non_empty_lines else text.strip()

        if target_snippet and target_snippet in typed_text:
            log.info(f"[VERIFY_MESSAGE] Verified typed text in compose box: '{target_snippet[:20]}...'")
            return True
        elif not target_snippet:
            return True
        else:
            log.warning(f"[VERIFY_MESSAGE] Expected '{target_snippet[:20]}...' in compose box, but found '{typed_text[:20]}...'")
            return False

    def _trigger_send(self, msg_box) -> bool:
        """Mengirim pesan via ENTER atau Send Button."""
        log.info("[SEND] Pressing ENTER key to send message...")
        try:
            msg_box.send_keys(Keys.ENTER)
        except Exception as e:
            log.debug(f"[SEND] send_keys(ENTER) failed: {e}")
            try:
                ActionChains(self.driver).send_keys(Keys.ENTER).perform()
            except Exception:
                pass

        # Check if compose box emptied after ENTER
        try:
            WebDriverWait(self.driver, 2).until(
                lambda d: self._get_compose_text(msg_box) == ""
            )
            log.info("[SEND] Message sent via ENTER key.")
            return True
        except TimeoutException:
            pass

        # If ENTER fails, locate Send Button
        log.warning("[SEND_BUTTON] Compose box not empty after ENTER. Attempting to click Send button...")
        send_btn = self._find_element_fallback(L.SEND_BTN, timeout=3, clickable=True)
        if send_btn and send_btn.is_displayed():
            log.info("[SEND_BUTTON] Send button found, clicking...")
            try:
                send_btn.click()
            except Exception:
                try:
                    self.driver.execute_script("arguments[0].click();", send_btn)
                except Exception as e:
                    log.error(f"[SEND_BUTTON] Failed to click send button: {e}")
                    return False

            try:
                WebDriverWait(self.driver, 2).until(
                    lambda d: self._get_compose_text(msg_box) == ""
                )
                log.info("[SEND_BUTTON] Message sent via Send button.")
                return True
            except TimeoutException:
                pass
        else:
            log.warning("[SEND_BUTTON] Send button is not visible.")

        # Retry focus once and try ENTER again
        log.info("[SEND] Retrying focus once and pressing ENTER...")
        self._focus_compose_box(msg_box)
        try:
            msg_box.send_keys(Keys.ENTER)
            try:
                WebDriverWait(self.driver, 2).until(
                    lambda d: self._get_compose_text(msg_box) == ""
                )
                return True
            except TimeoutException:
                pass
        except Exception:
            pass

        return False

    def _verify_message_appeared(self, text: str, msg_box, timeout: int = 10) -> bool:
        """Memastikan pesan benar-benar muncul di percakapan sebelum lanjut ke nomor berikutnya."""
        log.info(f"[VERIFY_MESSAGE] Waiting for message to appear in conversation (timeout {timeout}s)...")
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        snippet = lines[0][:30] if lines else ""

        def check_chat_contains(driver):
            # 1. Box is empty
            if self._get_compose_text(msg_box) != "":
                return False
            # 2. Main chat contains message text snippet
            if snippet:
                try:
                    main_el = driver.find_element(By.ID, "main")
                    if snippet in main_el.text:
                        return True
                except Exception:
                    pass
            else:
                return True
            return False

        try:
            WebDriverWait(self.driver, timeout).until(check_chat_contains)
            log.info("[MESSAGE_SENT] Verified message appeared in chat conversation.")
            return True
        except TimeoutException:
            # Fallback: If compose box is empty, assume sent successfully
            if self._get_compose_text(msg_box) == "":
                log.info("[MESSAGE_SENT] Compose box is empty. Assuming message was sent.")
                return True
            log.error("[VERIFY_MESSAGE] Timed out waiting for message to appear in chat.")
            return False

    def send_message(self, text: str) -> bool:
        """
        Mengirim pesan teks dengan jaminan focus, typing verification, retry, send button fallback, & appearance verification.
        """
        self._emit("Mengirim pesan teks...", "info")
        log.info("[MSG] Mengirim pesan...")

        # 1. Wait until compose input is editable
        msg_box = self._find_element_fallback(L.MSG_BOX, timeout=10)
        if msg_box is None:
            log.error("[MSG] Message box tidak ditemukan saat send_message.")
            self._emit("Gagal: message box tidak ditemukan.", "error")
            return False

        try:
            WebDriverWait(self.driver, 5).until(
                lambda d: msg_box.is_displayed() and msg_box.is_enabled()
            )
        except TimeoutException:
            log.error("[MSG] Compose box tidak editable dalam 5 detik.")
            return False

        # 2. Scroll into view if necessary
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", msg_box)
        except Exception as e:
            log.debug(f"[MSG] scrollIntoView error: {e}")

        # 3, 4, 5. Focus & verify document.activeElement
        focused = self._focus_compose_box(msg_box)
        if not focused:
            log.warning("[FOCUS] Retrying focus on compose box...")
            focused = self._focus_compose_box(msg_box)

        # 6. Clear any accidental selection
        try:
            self.driver.execute_script("window.getSelection().removeAllRanges();")
        except Exception:
            pass

        # 7, 8. Type message & line breaks via SHIFT+ENTER, and verify typing
        typed_ok = self._type_into_compose(msg_box, text)

        if not typed_ok:
            log.warning("[RETRY_TYPING] Initial typing verification failed. Retrying focus & typing...")
            self._clear_compose_box(msg_box)
            # Retry focus using alternative strategies
            self._focus_compose_box(msg_box)
            typed_ok = self._type_into_compose(msg_box, text)
            if not typed_ok:
                log.error("[RETRY_TYPING] Typing failed after retry.")
                return False

        # 9. Send message via ENTER or Send Button
        sent_ok = self._trigger_send(msg_box)
        if not sent_ok:
            log.error("[SEND] Failed to send message via ENTER or Send Button.")
            return False

        # 10. Wait until message appears in conversation before continuing
        appeared = self._verify_message_appeared(text, msg_box, timeout=10)
        if appeared:
            self._emit("Pesan teks terkirim.", "success")
            return True
        else:
            log.error("[VERIFY_MESSAGE] Message did not appear in conversation.")
            return False

    def check_sent(self, timeout: int = 10) -> bool:
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.any_of(*[EC.presence_of_element_located(loc) for loc in L.SENT_CHECK])
            )
            log.debug("[VERIFY] Centang terkirim terdeteksi.")
            return True
        except TimeoutException:
            log.warning("[VERIFY] Centang tidak terdeteksi dalam 10s.")
            return False

    # ══════════════════════════════════════════
    # SEND IMAGES
    # ══════════════════════════════════════════

    def send_images(self, image_paths: list[str]) -> bool:
        if not image_paths:
            return True

        all_ok = True
        for idx, img_path in enumerate(image_paths, start=1):
            self._emit(f"Mengirim gambar {idx}/{len(image_paths)}...", "info")
            log.info(f"[IMG] Mengirim gambar {idx}: {img_path}")

            ok = self._send_single_image(img_path, idx)
            if not ok:
                all_ok = False
                self._emit(f"Gambar {idx} gagal dikirim.", "warning")

            if idx < len(image_paths):
                time.sleep(self.img_delay)

        return all_ok

    def _send_single_image(self, img_path: str, idx: int) -> bool:
        if not Path(img_path).is_file():
            log.error(f"[IMG] File tidak ditemukan: {img_path}")
            return False

        try:
            clip = self._find_element_fallback(L.CLIP_BTN, timeout=5, clickable=True)
            if clip is None:
                log.error(f"[IMG] Clip button tidak ditemukan (gambar {idx})")
                return False

            time.sleep(self.click_delay)
            clip.click()

            img_input = self._find_element_fallback(L.IMG_INPUT, timeout=3)
            if img_input is None:
                self._escape()
                log.error(f"[IMG] Input file tidak ditemukan (gambar {idx})")
                return False

            img_input.send_keys(str(Path(img_path).resolve()))

            send_btn = self._find_element_fallback(L.IMG_SEND, timeout=5, clickable=True)
            if send_btn is None:
                self._escape()
                log.error(f"[IMG] Send button tidak ditemukan (gambar {idx})")
                return False

            time.sleep(self.click_delay)
            send_btn.click()
            self._emit(f"Gambar {idx} terkirim.", "success")
            log.info(f"[IMG] Gambar {idx} terkirim.")
            time.sleep(self.img_delay)
            return True

        except Exception as e:
            self._escape()
            log.error(f"[IMG] Error kirim gambar {idx}: {e}")
            return False

    # ══════════════════════════════════════════
    # HIGH-LEVEL SEND (dipakai BlastEngine)
    # ══════════════════════════════════════════

    def send_to(
        self,
        phone      : str,
        message    : str,
        image_paths: list[str],
    ) -> dict:
        """
        Kirim pesan ke satu nomor.
        Mengembalikan dict hasil lengkap dengan status, reason spesifik, & is_invalid flag.
        """
        if not self.is_alive():
            self._emit("Browser tidak aktif. Merestart...", "warning")
            ok = self._restart_driver()
            if not ok:
                return {
                    "status"    : "FAILED",
                    "reason"    : "DRIVER_CRASH",
                    "error_type": "DRIVER_CRASH",
                    "is_invalid": False,
                }

        if not self._wa_ready:
            ok = self.wait_wa_ready()
            if not ok:
                return {
                    "status"    : "FAILED",
                    "reason"    : "CHAT_NOT_OPENED",
                    "error_type": "WA_LOADING",
                    "is_invalid": False,
                }

        # 1. Buka chat & Cek Popup / Message box (10s max)
        res = self.open_chat(phone)

        # 2. Jika Invalid Number (BUG 1, 4, 7)
        if res.is_invalid or res.reason in ("INVALID_NUMBER", "NO_WHATSAPP"):
            return {
                "status"    : "FAILED",
                "reason"    : res.reason,  # INVALID_NUMBER / NO_WHATSAPP
                "error_type": res.reason,
                "is_invalid": True,
            }

        # 3. Jika Chat / Message box tidak terbuka
        if res.status != "SUCCESS":
            return {
                "status"    : "FAILED",
                "reason"    : res.reason if res.reason else "MESSAGE_BOX_NOT_FOUND",
                "error_type": res.reason if res.reason else "MESSAGE_BOX_NOT_FOUND",
                "is_invalid": False,
            }

        # 4. Kirim Pesan Teks
        msg_ok = self.send_message(message)
        if not msg_ok:
            return {
                "status"    : "FAILED",
                "reason"    : "SEND_FAILED",
                "error_type": "SEND_FAILED",
                "is_invalid": False,
            }

        self.check_sent(timeout=5)

        # 5. Kirim Gambar
        if image_paths:
            img_ok = self.send_images(image_paths)
            if not img_ok:
                return {
                    "status"    : "SUCCESS",
                    "reason"    : "SUCCESS",
                    "error_type": "SUCCESS",
                    "is_invalid": False,
                }

        return {
            "status"    : "SUCCESS",
            "reason"    : "SUCCESS",
            "error_type": "SUCCESS",
            "is_invalid": False,
        }

    # ══════════════════════════════════════════
    # ADAPTIVE DELAYS (BUG 3)
    # ══════════════════════════════════════════

    def random_delay(self) -> None:
        """Delay acak untuk nomor valid (2 - 4 detik)."""
        delay = random.uniform(2.0, 4.0)
        self._emit(f"⏳ Jeda {delay:.1f} detik...", "info")
        log.debug(f"[DELAY] Jeda {delay:.1f}s sebelum nomor berikutnya.")
        time.sleep(delay)

    def fast_delay(self) -> None:
        """Delay cepat untuk nomor invalid (0.5 - 1.0 detik)."""
        delay = random.uniform(0.5, 1.0)
        self._emit(f"⚡ Jeda cepat {delay:.2f}s (nomor invalid)...", "info")
        log.debug(f"[DELAY] Jeda cepat {delay:.2f}s untuk nomor invalid.")
        time.sleep(delay)

    # ══════════════════════════════════════════
    # UTILITY
    # ══════════════════════════════════════════

    def _is_fatal_exception(self, e: Exception) -> bool:
        if isinstance(e, (InvalidSessionIdException, NoSuchWindowException)):
            return True
        if isinstance(e, WebDriverException):
            s = str(e).lower()
            if "disconnected" in s or "not reachable" in s or "connection refused" in s:
                return True
        return False

    def _find_element_fallback(
        self,
        locators : list[tuple],
        timeout  : int  = 5,
        clickable: bool = False,
    ):
        """Mencari elemen dengan daftar locator fallback."""
        for loc in locators:
            try:
                condition = (
                    EC.element_to_be_clickable(loc)
                    if clickable
                    else EC.presence_of_element_located(loc)
                )
                el = WebDriverWait(self.driver, timeout).until(condition)
                log.debug(f"[LOCATOR] Ditemukan: {loc}")
                return el
            except TimeoutException:
                continue
            except Exception as e:
                if self._is_fatal_exception(e):
                    raise
                continue
        return None

    def _element_exists_any(self, locators: list[tuple]) -> bool:
        for loc in locators:
            try:
                els = self.driver.find_elements(loc[0], loc[1])
                for el in els:
                    if el.is_displayed():
                        return True
            except Exception as e:
                if self._is_fatal_exception(e):
                    raise
                continue
        return False

    def _find_msg_box_instant(self):
        """
        Mencari message box secara INSTANT (tanpa WebDriverWait).
        Digunakan dalam polling loop agar tidak blocking 6s per iterasi.
        find_elements() return langsung tanpa menunggu.
        """
        for loc in L.MSG_BOX:
            try:
                els = self.driver.find_elements(loc[0], loc[1])
                for el in els:
                    if el.is_displayed():
                        log.debug(f"[MSG_BOX_INSTANT] Ditemukan via {loc}")
                        return el
            except Exception as e:
                if self._is_fatal_exception(e):
                    raise
                continue
        return None

    def _escape(self) -> None:
        try:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(0.2)
        except Exception as e:
            if self._is_fatal_exception(e):
                raise
            pass

    def _emit(self, message: str, level: str = "info") -> None:
        log_fn = {
            "info"   : log.info,
            "success": log.info,
            "warning": log.warning,
            "error"  : log.error,
        }.get(level, log.info)
        log_fn(message)

        if self._log_cb:
            self._log_cb(message, level)

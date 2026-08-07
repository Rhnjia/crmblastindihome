/**
 * app.js — CRM Blast IndiHome Frontend Logic
 * ============================================
 * Mengelola semua interaksi UI:
 *   - AJAX polling status blast
 *   - SSE (Server-Sent Events) untuk console log realtime
 *   - Upload data pelanggan (paste/txt/excel)
 *   - Upload gambar
 *   - Start / Stop / Resume blast
 *   - Preview template
 *   - Export laporan
 *   - Update tabel hasil realtime
 *
 * Author  : CRM Team - PT Telkomsel Branch Karawang
 * Project : CRM Blast IndiHome
 */

"use strict";

/* ══════════════════════════════════════════════
   STATE
══════════════════════════════════════════════ */
const State = {
  currentMethod  : "paste",
  isRunning      : false,
  autoScroll     : true,
  logCount       : 0,
  allResults     : [],
  sseSource      : null,
  pollInterval   : null,
  uploadedImages : [],
};

/* ══════════════════════════════════════════════
   DOM HELPERS
══════════════════════════════════════════════ */
const $  = (id)  => document.getElementById(id);
const $$ = (sel) => document.querySelectorAll(sel);

/* ══════════════════════════════════════════════
   INIT
══════════════════════════════════════════════ */
document.addEventListener("DOMContentLoaded", () => {
  startClock();
  setupDragDrop();
  checkInitialStatus();  // Satu kali cek status, BUKAN polling
  connectSSE();
  updateDelayLabel();
});

/* ══════════════════════════════════════════════
   CLOCK
══════════════════════════════════════════════ */
function startClock() {
  const clockEl = $("navClock");
  function tick() {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString("id-ID", {
      hour  : "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }
  tick();
  setInterval(tick, 1000);
}

/* ══════════════════════════════════════════════
   INPUT METHOD SWITCH
══════════════════════════════════════════════ */
function switchInputMethod(method) {
  State.currentMethod = method;

  // Hide semua method panels
  ["paste", "txt", "excel"].forEach((m) => {
    const el = $(`method-${m}`);
    if (el) el.classList.toggle("d-none", m !== method);

    const tab = $(`tab-${m}`);
    if (tab) tab.classList.toggle("active", m === method);
  });
}

/* ══════════════════════════════════════════════
   LOAD DATA — PASTE
══════════════════════════════════════════════ */
function loadPasteData() {
  const text = $("pasteInput").value.trim();
  if (!text) {
    showToast("Teks paste kosong.", "warning");
    return;
  }

  // Hitung baris valid
  const lines = text
    .split("\n")
    .filter((l) => l.trim().split(/\s+/).length >= 2);

  showDataStatus(lines.length);
  showToast(`${lines.length} pelanggan dimuat dari paste.`, "success");
}

/* ══════════════════════════════════════════════
   UPLOAD DATA FILE (TXT / EXCEL)
══════════════════════════════════════════════ */
function uploadDataFile(type) {
  const inputId = type === "txt" ? "txtFileInput" : "excelFileInput";
  const fileEl  = $(inputId);
  const file    = fileEl?.files?.[0];

  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);
  formData.append("method", type);

  showToast(`Mengupload ${file.name}...`, "info");

  fetch("/api/upload-data", { method: "POST", body: formData })
    .then((r) => r.json())
    .then((data) => {
      if (data.ok) {
        showDataStatus(data.count);
        showToast(data.message, "success");
        // Render preview mini table
        if (data.preview?.length) {
          renderDataPreview(data.preview);
        }
      } else {
        showToast(data.message || "Upload gagal.", "danger");
      }
    })
    .catch((err) => {
      console.error("Upload error:", err);
      showToast("Koneksi error saat upload.", "danger");
    });
}

function showDataStatus(count) {
  const el    = $("dataStatus");
  const label = $("dataStatusText");
  if (el && label) {
    el.classList.remove("d-none");
    label.textContent = `${count} pelanggan dimuat`;
  }
}

function renderDataPreview(rows) {
  // Tampilkan preview singkat di console
  appendConsole(`📋 Preview data: ${rows.length} baris pertama`, "info");
  rows.forEach((r, i) => {
    appendConsole(
      `  [${i + 1}] IndiHome: ${r.nomor_indihome || "-"} | WA: ${r.nomor_wa || "-"} | Nama: ${r.nama || "-"}`,
      "info"
    );
  });
}

/* ══════════════════════════════════════════════
   UPLOAD GAMBAR
══════════════════════════════════════════════ */
function uploadImages() {
  const input = $("imgFileInput");
  const files = Array.from(input.files || []);

  if (!files.length) return;

  const formData = new FormData();
  files.forEach((f) => formData.append("files[]", f));

  fetch("/api/upload-image", { method: "POST", body: formData })
    .then((r) => r.json())
    .then((data) => {
      if (data.ok) {
        State.uploadedImages = data.paths || [];
        renderImagePreviews(files);
        $("clearImgBtn")?.classList.remove("d-none");
        showToast(data.message, "success");
      } else {
        showToast(data.message || "Upload gambar gagal.", "danger");
      }
    })
    .catch(() => showToast("Error upload gambar.", "danger"));
}

function renderImagePreviews(files) {
  const container = $("imagePreviewContainer");
  if (!container) return;

  container.innerHTML = "";
  files.forEach((file) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const img   = document.createElement("img");
      img.src     = e.target.result;
      img.className = "image-thumb";
      img.title   = file.name;
      container.appendChild(img);
    };
    reader.readAsDataURL(file);
  });
}

function clearImages() {
  fetch("/api/clear-images", { method: "POST" })
    .then((r) => r.json())
    .then((data) => {
      if (data.ok) {
        State.uploadedImages = [];
        const container = $("imagePreviewContainer");
        if (container) container.innerHTML = "";
        $("clearImgBtn")?.classList.add("d-none");
        $("imgFileInput").value = "";
        showToast("Gambar dihapus.", "info");
      }
    });
}

/* ══════════════════════════════════════════════
   TEMPLATE
══════════════════════════════════════════════ */
function insertPlaceholder(placeholder) {
  const textarea = $("templateInput");
  if (!textarea) return;

  const start = textarea.selectionStart;
  const end   = textarea.selectionEnd;
  const text  = textarea.value;

  textarea.value        = text.slice(0, start) + placeholder + text.slice(end);
  textarea.selectionEnd = start + placeholder.length;
  textarea.focus();
}

function clearTemplate() {
  if (confirm("Hapus template? Tindakan ini tidak dapat dibatalkan.")) {
    $("templateInput").value = "";
  }
}

function previewTemplate() {
  const template = $("templateInput")?.value || "";
  if (!template.trim()) {
    showToast("Template kosong.", "warning");
    return;
  }

  fetch("/api/preview-template", {
    method : "POST",
    headers: { "Content-Type": "application/json" },
    body   : JSON.stringify({ template }),
  })
    .then((r) => r.json())
    .then((data) => {
      const previewEl  = $("previewContent");
      const warnEl     = $("previewWarnings");
      const warnList   = $("previewWarningList");

      if (previewEl) {
        previewEl.textContent = data.preview || "(kosong)";
      }

      if (data.warnings?.length) {
        warnEl?.classList.remove("d-none");
        if (warnList) warnList.textContent = data.warnings.join(", ");
      } else {
        warnEl?.classList.add("d-none");
      }

      // Buka modal
      const modal = new bootstrap.Modal($("templatePreviewModal"));
      modal.show();
    })
    .catch(() => showToast("Gagal memuat preview.", "danger"));
}

/* ══════════════════════════════════════════════
   BLAST CONTROL
══════════════════════════════════════════════ */
function startBlast() {
  const template = $("templateInput")?.value?.trim();
  if (!template) {
    showToast("Template pesan kosong.", "warning");
    return;
  }

  const inputType = State.currentMethod === "paste" ? "paste" : "data";
  const pasteText = $("pasteInput")?.value?.trim() || "";

  if (inputType === "paste" && !pasteText) {
    showToast("Data paste kosong.", "warning");
    return;
  }

  const settings = {
    delay_min: parseInt($("delayMin")?.value || "5"),
    delay_max: parseInt($("delayMax")?.value || "10"),
    retry_max: parseInt($("retryMax")?.value || "3"),
    img_delay: parseFloat($("imgDelay")?.value || "2"),
  };

  const payload = {
    input_type: inputType,
    paste_text: pasteText,
    template,
    settings,
  };

  fetch("/api/start", {
    method : "POST",
    headers: { "Content-Type": "application/json" },
    body   : JSON.stringify(payload),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.ok) {
        showToast(data.message, "success");
        appendConsole(`🚀 Blast dimulai: ${data.total} pelanggan`, "success");
        setBlastRunning(true);
      } else {
        showToast(data.message || "Gagal memulai blast.", "danger");
      }
    })
    .catch((err) => {
      console.error(err);
      showToast("Koneksi error.", "danger");
    });
}

function stopBlast() {
  fetch("/api/stop", { method: "POST" })
    .then((r) => r.json())
    .then((data) => {
      showToast(data.message, data.ok ? "warning" : "danger");
      if (data.ok) {
        appendConsole("⏹ Blast dihentikan oleh pengguna.", "warning");
        setBlastRunning(false);
      }
    })
    .catch(() => showToast("Error menghentikan blast.", "danger"));
}

function resumeBlast() {
  const template = $("templateInput")?.value?.trim() || "";

  fetch("/api/resume", {
    method : "POST",
    headers: { "Content-Type": "application/json" },
    body   : JSON.stringify({ template }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.ok) {
        showToast(data.message, "success");
        appendConsole("▶ Blast dilanjutkan dari posisi terakhir.", "success");
        setBlastRunning(true);
      } else {
        showToast(data.message || "Resume gagal.", "danger");
      }
    })
    .catch(() => showToast("Error resume blast.", "danger"));
}

function exportReport() {
  window.location.href = "/api/export";
  showToast("Mendownload laporan Excel...", "info");
}

/* ══════════════════════════════════════════════
   SSE — CONSOLE LOG REALTIME
══════════════════════════════════════════════ */
function connectSSE() {
  if (State.sseSource) {
    State.sseSource.close();
  }

  State.sseSource = new EventSource("/api/logs");

  State.sseSource.onmessage = (event) => {
    try {
      const item = JSON.parse(event.data);

      if (item.type === "heartbeat") return;

      if (item.type === "log") {
        appendConsole(item.message, item.level, item.timestamp);
      }

      if (item.type === "done") {
        appendConsole("🎉 Blast selesai!", "success");
        setBlastRunning(false);
        enableExport(true);
        enableResume(false);
      }

    } catch (e) {
      // Abaikan parse error dari heartbeat
    }
  };

  State.sseSource.onerror = () => {
    // Reconnect setelah 3 detik
    setTimeout(connectSSE, 3000);
  };
}

/* ══════════════════════════════════════════════
   POLLING — STATUS UPDATE
══════════════════════════════════════════════ */

/**
 * Cek status SATU KALI saat page load.
 * Jika blast ternyata sedang RUNNING, baru mulai polling.
 * Jika IDLE/DONE/STOPPED, set tombol ke state awal tanpa polling.
 */
function checkInitialStatus() {
  fetch("/api/status")
    .then((r) => r.json())
    .then((data) => {
      updateStatsCards(data);
      updateProgressBar(data);
      updateNavStatus(data.status);
      updateResultTable(data.results || []);

      if (data.has_resume) enableResume(true);
      if (data.results?.length > 0) enableExport(true);

      // Jika blast sedang RUNNING, sinkronkan UI dan mulai polling
      if (data.status === "RUNNING") {
        setBlastRunning(true);
      } else {
        // Page load normal — tombol dalam keadaan default
        setBlastRunning(false);
      }
    })
    .catch(() => {
      // Server belum siap — set tombol ke default
      setBlastRunning(false);
    });
}

/**
 * Mulai polling HANYA saat blast sedang berjalan.
 * Dipanggil dari setBlastRunning(true).
 */
function startPolling() {
  // Jangan buat interval ganda
  if (State.pollInterval) return;
  State.pollInterval = setInterval(pollStatus, 2000);
}

/**
 * Hentikan polling. Dipanggil saat blast selesai/stop.
 */
function stopPolling() {
  if (State.pollInterval) {
    clearInterval(State.pollInterval);
    State.pollInterval = null;
  }
}

function pollStatus() {
  fetch("/api/status")
    .then((r) => r.json())
    .then((data) => {
      updateStatsCards(data);
      updateProgressBar(data);
      updateNavStatus(data.status);
      updateResultTable(data.results || []);

      if (data.has_resume) enableResume(true);
      if (data.results?.length > 0) enableExport(true);

      // Auto-stop polling jika backend sudah selesai/berhenti
      if (["DONE", "STOPPED", "IDLE"].includes(data.status)) {
        if (State.isRunning) {
          setBlastRunning(false);  // Ini juga memanggil stopPolling()
        }
      }
    })
    .catch(() => {
      // Fail gracefully — JANGAN tampilkan toast error
      // Hanya silent fail
    });
}

/* ══════════════════════════════════════════════
   UI UPDATES
══════════════════════════════════════════════ */
function updateStatsCards(data) {
  animateNumber("statTotal",    data.total    || 0);
  animateNumber("statSuccess",  data.success  || 0);
  animateNumber("statFailed",   data.failed   || 0);
  animateNumber("statSkipped",  data.skipped  || 0);
  $("statProgress").textContent = (data.progress || 0) + "%";
}

function animateNumber(id, target) {
  const el = $(id);
  if (!el) return;
  const current = parseInt(el.textContent) || 0;
  if (current === target) return;
  el.textContent = target;
  el.style.transform = "scale(1.1)";
  setTimeout(() => { el.style.transform = "scale(1)"; }, 200);
}

function updateProgressBar(data) {
  const bar   = $("progressBar");
  const label = $("progressLabel");
  const pct   = data.progress || 0;

  if (bar) {
    bar.style.width = pct + "%";
  }

  const done = (data.success || 0) + (data.failed || 0) + (data.skipped || 0);
  if (label) label.textContent = `${done} / ${data.total || 0} terkirim`;

  const statusText = $("blastStatusText");
  if (statusText) statusText.textContent = data.status || "IDLE";
}

function updateNavStatus(status) {
  const pill = $("navStatusPill");
  const text = $("navStatusText");

  if (!text) return;
  text.textContent = status || "IDLE";

  if (!pill) return;
  pill.classList.remove("running", "stopped");

  if (status === "RUNNING") {
    pill.classList.add("running");
  } else if (["STOPPED", "FAILED"].includes(status)) {
    pill.classList.add("stopped");
  }
}

/* ── Result Table Update ────────────────────────── */
let _lastResultCount = 0;

function updateResultTable(results) {
  if (results.length === _lastResultCount) return;
  _lastResultCount = results.length;

  State.allResults = results;
  renderTable(results);
}

function renderTable(results) {
  const tbody = $("resultTableBody");
  if (!tbody) return;

  if (!results.length) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="text-center text-muted py-4">
          <i class="bi bi-inbox display-6 d-block mb-2"></i>
          Belum ada data.
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = results.map((r) => {
    const statusBadge = `<span class="s-badge ${r.status}">${r.status}</span>`;
    return `
      <tr>
        <td>${r.num || "-"}</td>
        <td><code>${r.nomor_indihome || "-"}</code></td>
        <td><code>${r.nomor_wa || "-"}</code></td>
        <td>${r.nama || "-"}</td>
        <td>${statusBadge}</td>
        <td>${r.jam_kirim || "-"}</td>
        <td class="text-center">${r.percobaan || 1}</td>
        <td class="text-muted">${r.keterangan || "-"}</td>
      </tr>`;
  }).join("");
}

function filterTable() {
  const search = $("tableSearch")?.value?.toLowerCase() || "";
  const filter = $("tableFilter")?.value || "";

  const filtered = State.allResults.filter((r) => {
    const matchSearch =
      !search ||
      (r.nomor_indihome || "").includes(search) ||
      (r.nomor_wa       || "").includes(search) ||
      (r.nama           || "").toLowerCase().includes(search);

    const matchFilter = !filter || r.status === filter;

    return matchSearch && matchFilter;
  });

  renderTable(filtered);
}

/* ══════════════════════════════════════════════
   CONSOLE
══════════════════════════════════════════════ */
function appendConsole(message, level = "info", timestamp = null) {
  const container = $("consoleContainer");
  if (!container) return;

  if (!timestamp) {
    const now = new Date();
    timestamp = now.toLocaleTimeString("id-ID", {
      hour  : "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  const line = document.createElement("div");
  line.className = "console-line";
  line.innerHTML = `
    <span class="c-time">${timestamp}</span>
    <span class="c-level ${level}">[${level.toUpperCase()}]</span>
    <span class="c-msg ${level}">${escapeHtml(message)}</span>`;

  container.appendChild(line);

  // Auto scroll
  if (State.autoScroll) {
    container.scrollTop = container.scrollHeight;
  }

  // Update log count badge
  State.logCount++;
  const badge = $("logCountBadge");
  if (badge) badge.textContent = `${State.logCount} entries`;

  // Hapus line lama jika terlalu banyak (max 500)
  while (container.children.length > 500) {
    container.removeChild(container.firstChild);
  }
}

function clearConsole() {
  const container = $("consoleContainer");
  if (container) container.innerHTML = "";
  State.logCount = 0;
  const badge = $("logCountBadge");
  if (badge) badge.textContent = "0 entries";
}

function toggleAutoScroll() {
  State.autoScroll = !State.autoScroll;
  const btn = $("btnAutoScroll");
  if (btn) {
    btn.classList.toggle("btn-outline-secondary", !State.autoScroll);
    btn.classList.toggle("btn-success",            State.autoScroll);
  }
}

/* ══════════════════════════════════════════════
   BUTTON STATE MANAGEMENT
══════════════════════════════════════════════ */
function setBlastRunning(running) {
  State.isRunning = running;

  const btnStart = $("btnStart");
  const btnStop  = $("btnStop");

  if (btnStart) {
    btnStart.disabled = running;
    btnStart.innerHTML = running
      ? `<i class="bi bi-hourglass-split spin-pulse me-2"></i>Sedang Blast...`
      : `<i class="bi bi-send-fill me-2"></i>Mulai Blast`;
  }

  if (btnStop) btnStop.disabled = !running;
  document.body.classList.toggle("blast-running", running);

  // Kelola lifecycle polling:
  // RUNNING  → mulai polling
  // STOPPED  → hentikan polling
  if (running) {
    startPolling();
  } else {
    stopPolling();
  }
}

function enableResume(enabled) {
  const btn = $("btnResume");
  if (btn) btn.disabled = !enabled;
}

function enableExport(enabled) {
  const btn = $("btnExport");
  if (btn) btn.disabled = !enabled;
}

/* ══════════════════════════════════════════════
   DELAY LABEL
══════════════════════════════════════════════ */
function updateDelayLabel() {
  const min = $("delayMin")?.value || "5";
  const max = $("delayMax")?.value || "10";
  const lbl = $("delayLabel");
  if (lbl) lbl.textContent = `${min}–${max} detik`;
}

/* ══════════════════════════════════════════════
   DRAG & DROP
══════════════════════════════════════════════ */
function setupDragDrop() {
  setupZone("dropZoneTxt",   "txtFileInput",   uploadDataFile.bind(null, "txt"));
  setupZone("dropZoneExcel", "excelFileInput", uploadDataFile.bind(null, "excel"));
  setupZone("dropZoneImg",   "imgFileInput",   uploadImages);
}

function setupZone(zoneId, inputId, handler) {
  const zone = $(zoneId);
  if (!zone) return;

  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("drag-over");
  });

  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));

  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    const input = $(inputId);
    if (input && e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      handler();
    }
  });
}

/* ══════════════════════════════════════════════
   TOAST NOTIFICATIONS
══════════════════════════════════════════════ */
function showToast(message, type = "info") {
  const container = $("toastContainer");
  if (!container) return;

  const toastEl = document.createElement("div");
  toastEl.className = `toast toast-${type} align-items-center text-bg-dark border-0 show`;
  toastEl.setAttribute("role", "alert");
  toastEl.innerHTML = `
    <div class="d-flex">
      <div class="toast-body">
        <i class="bi bi-${_toastIcon(type)} me-2"></i>${escapeHtml(message)}
      </div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto"
              data-bs-dismiss="toast"></button>
    </div>`;

  container.appendChild(toastEl);

  // Auto dismiss setelah 4 detik
  setTimeout(() => {
    toastEl.classList.remove("show");
    setTimeout(() => toastEl.remove(), 300);
  }, 4000);
}

function _toastIcon(type) {
  const icons = {
    success: "check-circle-fill",
    danger : "x-circle-fill",
    warning: "exclamation-triangle-fill",
    info   : "info-circle-fill",
  };
  return icons[type] || "info-circle-fill";
}

/* ══════════════════════════════════════════════
   UTILITIES
══════════════════════════════════════════════ */
function escapeHtml(text) {
  const map = {
    "&" : "&amp;",
    "<" : "&lt;",
    ">" : "&gt;",
    '"' : "&quot;",
    "'" : "&#039;",
  };
  return String(text).replace(/[&<>"']/g, (m) => map[m]);
}

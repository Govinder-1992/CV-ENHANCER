/* CV Enhancer – frontend logic
 * - Validates the uploaded CV (PDF/DOCX, size) and form fields in the browser.
 * - Sends the CV (base64) + job details to Amazon API Gateway as JSON.
 *   The original file is never pushed straight to S3 from the browser.
 * - Shows upload validation, loading, processing progress, errors, and the
 *   final download link.
 */
(function () {
  "use strict";

  const CFG = window.CV_ENHANCER_CONFIG || {};
  const MAX_BYTES = (CFG.MAX_FILE_SIZE_MB || 5) * 1024 * 1024;
  const ALLOWED = CFG.ALLOWED_EXTENSIONS || ["pdf", "docx"];
  const POLL_INTERVAL = CFG.POLL_INTERVAL_MS || 3000;
  const POLL_MAX = CFG.POLL_MAX_ATTEMPTS || 40;

  // ---- DOM refs ----
  const form = document.getElementById("cv-form");
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("cv-file");
  const fileInfo = document.getElementById("file-info");
  const fileNameEl = document.getElementById("file-name");
  const fileSizeEl = document.getElementById("file-size");
  const removeFileBtn = document.getElementById("remove-file");

  const roleInput = document.getElementById("job-role");
  const descInput = document.getElementById("job-description");
  const descCount = document.getElementById("desc-count");
  const emailInput = document.getElementById("email");

  const submitBtn = document.getElementById("submit-btn");

  const statusPanel = document.getElementById("status-panel");
  const statusIcon = document.getElementById("status-icon");
  const statusText = document.getElementById("status-text");
  const progressTrack = document.getElementById("progress-track");
  const progressBar = document.getElementById("progress-bar");
  const resultBox = document.getElementById("result-box");
  const downloadLink = document.getElementById("download-link");

  const errors = {
    file: document.getElementById("file-error"),
    role: document.getElementById("role-error"),
    desc: document.getElementById("desc-error"),
    email: document.getElementById("email-error"),
  };

  let selectedFile = null;
  let submitting = false;

  document.getElementById("year").textContent = new Date().getFullYear();

  // Show the real upload limit in the dropzone hint.
  const dzHint = document.getElementById("dz-hint");
  if (dzHint) dzHint.textContent = ALLOWED.join(" or ").toUpperCase() + ", up to " + formatSize(MAX_BYTES);

  // ---- Helpers ----
  function getExt(name) {
    const i = name.lastIndexOf(".");
    return i >= 0 ? name.slice(i + 1).toLowerCase() : "";
  }

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(2) + " MB";
  }

  function setFieldError(key, input, message) {
    if (errors[key]) errors[key].textContent = message || "";
    if (input) input.classList.toggle("invalid", !!message);
  }

  function validEmail(value) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
  }

  // ---- File validation + selection ----
  function validateFile(file) {
    if (!file) return "Please upload your CV.";
    const ext = getExt(file.name);
    if (!ALLOWED.includes(ext)) {
      return "Unsupported file type. Please upload a " + ALLOWED.join(" or ").toUpperCase() + " file.";
    }
    if (file.size > MAX_BYTES) {
      return "File is too large (" + formatSize(file.size) + "). Max is " + formatSize(MAX_BYTES) + ".";
    }
    if (file.size === 0) return "This file appears to be empty.";
    return "";
  }

  function handleFile(file) {
    const err = validateFile(file);
    if (err) {
      selectedFile = null;
      fileInput.value = "";
      fileInfo.hidden = true;
      dropzone.classList.add("invalid");
      setFieldError("file", null, err);
      return;
    }
    selectedFile = file;
    fileNameEl.textContent = file.name;
    fileSizeEl.textContent = "(" + formatSize(file.size) + ")";
    fileInfo.hidden = false;
    dropzone.classList.remove("invalid");
    setFieldError("file", null, "");
  }

  function clearFile() {
    selectedFile = null;
    fileInput.value = "";
    fileInfo.hidden = true;
    setFieldError("file", null, "");
  }

  // ---- Dropzone events ----
  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files[0]) handleFile(fileInput.files[0]);
  });
  removeFileBtn.addEventListener("click", clearFile);

  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    })
  );
  dropzone.addEventListener("drop", (e) => {
    const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) handleFile(file);
  });

  // ---- Live field feedback ----
  descInput.addEventListener("input", () => {
    descCount.textContent = descInput.value.trim().length + " characters";
    if (descInput.value.trim()) setFieldError("desc", descInput, "");
  });
  roleInput.addEventListener("input", () => {
    if (roleInput.value.trim()) setFieldError("role", roleInput, "");
  });
  emailInput.addEventListener("input", () => {
    if (validEmail(emailInput.value)) setFieldError("email", emailInput, "");
  });

  // ---- Status UI ----
  function showStatus(kind, message) {
    statusPanel.hidden = false;
    statusPanel.classList.remove("loading", "is-error", "is-success");
    if (kind === "loading") {
      statusPanel.classList.add("loading");
      statusIcon.textContent = "";
    } else if (kind === "error") {
      statusPanel.classList.add("is-error");
      statusIcon.textContent = "!";
    } else if (kind === "success") {
      statusPanel.classList.add("is-success");
      statusIcon.textContent = "\u2713";
    }
    statusText.textContent = message;
  }

  function setProgress(pct) {
    if (pct == null) {
      progressTrack.hidden = true;
      return;
    }
    progressTrack.hidden = false;
    progressBar.style.width = Math.max(0, Math.min(100, pct)) + "%";
  }

  function setLoading(isLoading) {
    submitting = isLoading;
    submitBtn.disabled = isLoading;
    submitBtn.classList.toggle("loading", isLoading);
    submitBtn.querySelector(".btn-label").textContent = isLoading ? "Analyzing..." : "Analyze CV";
  }

  // ---- Read file as base64 (no raw upload to S3 from the browser) ----
  function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result || "";
        const comma = result.indexOf(",");
        resolve(comma >= 0 ? result.slice(comma + 1) : result);
      };
      reader.onerror = () => reject(new Error("Could not read the file."));
      reader.readAsDataURL(file);
    });
  }

  // ---- Validate whole form ----
  function validateForm() {
    let ok = true;

    const fileErr = validateFile(selectedFile);
    if (fileErr) {
      setFieldError("file", null, fileErr);
      dropzone.classList.add("invalid");
      ok = false;
    }

    if (!roleInput.value.trim()) {
      setFieldError("role", roleInput, "Please enter your desired job role.");
      ok = false;
    }

    if (!descInput.value.trim()) {
      setFieldError("desc", descInput, "Please paste the job description.");
      ok = false;
    } else if (descInput.value.trim().length < 20) {
      setFieldError("desc", descInput, "Please provide a bit more detail (at least 20 characters).");
      ok = false;
    }

    if (!emailInput.value.trim()) {
      setFieldError("email", emailInput, "Please enter your email address.");
      ok = false;
    } else if (!validEmail(emailInput.value)) {
      setFieldError("email", emailInput, "Please enter a valid email address.");
      ok = false;
    }

    return ok;
  }

  // ---- Network: send to API Gateway ----
  function buildHeaders() {
    const headers = { "Content-Type": "application/json" };
    if (CFG.API_KEY) headers["x-api-key"] = CFG.API_KEY;
    return headers;
  }

  async function sendToApi(payload) {
    if (!CFG.API_ENDPOINT || CFG.API_ENDPOINT.indexOf("YOUR_API_ID") !== -1) {
      throw new Error("API endpoint is not configured. Set API_ENDPOINT in config.js.");
    }
    const res = await fetch(CFG.API_ENDPOINT, {
      method: "POST",
      headers: buildHeaders(),
      body: JSON.stringify(payload),
    });

    let data = null;
    const text = await res.text();
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {
      data = { message: text };
    }

    if (!res.ok) {
      const msg = (data && (data.message || data.error)) || "Request failed (" + res.status + ").";
      throw new Error(msg);
    }
    return data;
  }

  function extractDownloadUrl(data) {
    return (
      data && (data.downloadUrl || data.downloadLink || data.url || data.enhancedCvUrl || data.presignedUrl)
    );
  }

  // Poll a status URL until the enhanced CV is ready.
  async function pollForResult(statusUrl) {
    for (let attempt = 1; attempt <= POLL_MAX; attempt++) {
      const pct = Math.min(95, 40 + Math.round((attempt / POLL_MAX) * 55));
      setProgress(pct);
      showStatus("loading", "Processing your CV... (" + attempt + "/" + POLL_MAX + ")");

      await new Promise((r) => setTimeout(r, POLL_INTERVAL));

      let data;
      try {
        const res = await fetch(statusUrl, { headers: buildHeaders() });
        data = await res.json();
      } catch (_) {
        continue; // transient error, keep polling
      }

      const status = (data.status || "").toLowerCase();
      const url = extractDownloadUrl(data);

      if (url || status === "complete" || status === "completed" || status === "done") {
        return url;
      }
      if (status === "failed" || status === "error") {
        throw new Error(data.message || "Processing failed on the server.");
      }
    }
    throw new Error("Processing is taking longer than expected. Please check your email shortly.");
  }

  function finishSuccess(url) {
    setProgress(100);
    showStatus("success", "Done! We've also emailed a copy to " + emailInput.value.trim() + ".");
    if (url) {
      downloadLink.href = url;
      resultBox.hidden = false;
    } else {
      resultBox.hidden = true;
    }
  }

  // ---- Submit ----
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (submitting) return;

    resultBox.hidden = true;
    setProgress(null);

    if (!validateForm()) {
      showStatus("error", "Please fix the highlighted fields and try again.");
      return;
    }

    setLoading(true);
    showStatus("loading", "Validating and preparing your CV...");
    setProgress(10);

    try {
      const base64 = await readFileAsBase64(selectedFile);
      setProgress(30);
      showStatus("loading", "Sending your CV for analysis...");

      const payload = {
        fileName: selectedFile.name,
        fileType: getExt(selectedFile.name),
        contentType: selectedFile.type || "application/octet-stream",
        fileSize: selectedFile.size,
        // base64 content so the browser never PUTs the raw file to S3 directly.
        fileContentBase64: base64,
        jobRole: roleInput.value.trim(),
        jobDescription: descInput.value.trim(),
        email: emailInput.value.trim(),
        submittedAt: new Date().toISOString(),
      };

      const data = await sendToApi(payload);
      setProgress(40);

      const directUrl = extractDownloadUrl(data);
      if (directUrl) {
        finishSuccess(directUrl);
        return;
      }

      // Async flow: poll for completion if the API returned a status URL.
      const statusUrl = data.statusUrl || data.pollUrl;
      if (statusUrl) {
        const url = await pollForResult(statusUrl);
        finishSuccess(url);
        return;
      }

      // Accepted for processing, result will arrive by email (SQS async flow).
      var ref = data.requestId ? " (request ID: " + data.requestId + ")" : "";
      showStatus(
        "success",
        "Your CV has been submitted for processing. We'll email the enhanced CV to " +
          emailInput.value.trim() +
          " when it's ready." +
          ref
      );
      setProgress(100);
    } catch (err) {
      showStatus("error", err && err.message ? err.message : "Something went wrong. Please try again.");
      setProgress(null);
    } finally {
      setLoading(false);
    }
  });
})();

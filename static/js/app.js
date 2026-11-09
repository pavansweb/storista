/**
 * Storista — Interactive Application Core
 * static/js/app.js
 * Implements Features 12, 13, 14, 16, 17, 19, 20
 */

document.addEventListener('DOMContentLoaded', () => {
  'use strict';

  // ==========================================================================
  // 1. Utilities & Formatters
  // ==========================================================================
  function formatBytes(bytes) {
    if (!bytes || bytes === 0 || isNaN(bytes)) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  function getFileExtension(filename) {
    if (!filename) return '';
    const parts = filename.split('.');
    return parts.length > 1 ? parts.pop().toLowerCase() : '';
  }

  // ==========================================================================
  // 2. Toast Notification System (Feature 17)
  // ==========================================================================
  const toastContainer = document.getElementById('toastContainer');

  function showToast(type, message, title = '') {
    if (!toastContainer) return;

    const icons = {
      success: 'bi-check-circle-fill text-success',
      danger: 'bi-exclamation-octagon-fill text-danger',
      warning: 'bi-exclamation-triangle-fill text-warning',
      info: 'bi-info-circle-fill text-primary',
    };

    const iconClass = icons[type] || icons.info;
    const safeType = Object.prototype.hasOwnProperty.call(icons, type) ? type : 'info';

    const toast = document.createElement('div');
    toast.className = `glass-toast toast-border-${safeType} p-3 show`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');

    // Safe DOM construction: create elements and set textContent to prevent DOM XSS
    const wrapper = document.createElement('div');
    wrapper.className = 'd-flex align-items-center gap-2';

    const iconEl = document.createElement('i');
    iconEl.className = `bi ${iconClass} fs-5 flex-shrink-0`;
    iconEl.setAttribute('aria-hidden', 'true');
    wrapper.appendChild(iconEl);

    const bodyDiv = document.createElement('div');
    bodyDiv.className = 'flex-grow-1 overflow-hidden';

    if (title) {
      const titleDiv = document.createElement('div');
      titleDiv.className = 'fw-bold small text-white';
      titleDiv.textContent = title;
      bodyDiv.appendChild(titleDiv);
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = 'small text-light text-break';
    messageDiv.textContent = message;
    bodyDiv.appendChild(messageDiv);

    wrapper.appendChild(bodyDiv);

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn-close-toast ms-2';
    closeBtn.setAttribute('aria-label', 'Close notification');

    const closeIcon = document.createElement('i');
    closeIcon.className = 'bi bi-x';
    closeIcon.setAttribute('aria-hidden', 'true');
    closeBtn.appendChild(closeIcon);

    wrapper.appendChild(closeBtn);
    toast.appendChild(wrapper);
    toastContainer.appendChild(toast);

    const dismiss = () => {
      toast.classList.remove('show');
      toast.classList.add('hide');
      setTimeout(() => {
        if (typeof toast.remove === 'function') {
          toast.remove();
        } else if (toast.parentElement) {
          toast.parentElement.removeChild(toast);
        }
      }, 250);
    };

    closeBtn.addEventListener('click', dismiss);
    setTimeout(dismiss, 4500);
  }

  // Expose globally
  window.showToast = showToast;

  // ==========================================================================
  // 3. Tab Switching Architecture (Feature 13)
  // ==========================================================================
  const tabBtns = document.querySelectorAll('.upload-tabs .tab-btn');
  const panelFileUpload = document.getElementById('panel-file-upload');
  const panelUrlUpload = document.getElementById('panel-url-upload');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
      });
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');

      const targetTab = btn.dataset.tab;
      if (targetTab === 'file') {
        panelFileUpload?.classList.remove('d-none');
        panelFileUpload?.classList.add('active');
        panelUrlUpload?.classList.add('d-none');
        panelUrlUpload?.classList.remove('active');
      } else {
        panelUrlUpload?.classList.remove('d-none');
        panelUrlUpload?.classList.add('active');
        panelFileUpload?.classList.add('d-none');
        panelFileUpload?.classList.remove('active');
        document.getElementById('urlInput')?.focus();
      }
    });
  });

  // ==========================================================================
  // 4. Drag & Drop Engine (Feature 12) & File Selection
  // ==========================================================================
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const dropText = document.getElementById('dropText');
  const dropIcon = document.getElementById('dropIcon');
  const selectedFileInfo = document.getElementById('selectedFileInfo');
  const selectedFileName = document.getElementById('selectedFileName');
  const selectedFileSize = document.getElementById('selectedFileSize');
  const clearFileBtn = document.getElementById('clearFileBtn');
  const fileSubmitBtn = document.getElementById('fileSubmitBtn');
  const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

  // Prevent default drag events on window to protect against navigating away
  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    window.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
    }, false);
  });

  let dragCounter = 0;

  if (dropZone) {
    dropZone.addEventListener('click', () => fileInput?.click());
    dropZone.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        fileInput?.click();
      }
    });

    dropZone.addEventListener('dragenter', () => {
      dragCounter++;
      dropZone.classList.add('drag-active');
      if (dropIcon) dropIcon.className = 'bi bi-cloud-arrow-up-fill text-primary';
      if (dropText) dropText.textContent = 'Release to drop file';
    });

    dropZone.addEventListener('dragover', (e) => {
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = 'copy';
      }
      dropZone.classList.add('drag-active');
    });

    dropZone.addEventListener('dragleave', () => {
      dragCounter--;
      if (dragCounter <= 0) {
        dragCounter = 0;
        dropZone.classList.remove('drag-active');
        if (dropIcon) dropIcon.className = 'bi bi-cloud-arrow-up';
        if (dropText) dropText.textContent = 'Click or drag file here';
      }
    });

    dropZone.addEventListener('drop', (e) => {
      dragCounter = 0;
      dropZone.classList.remove('drag-active');
      if (dropIcon) dropIcon.className = 'bi bi-cloud-arrow-up';
      if (dropText) dropText.textContent = 'Click or drag file here';

      const files = e.dataTransfer?.files;
      if (files && files.length > 0) {
        // Set the input file list if supported
        try {
          const dataTransfer = new DataTransfer();
          dataTransfer.items.add(files[0]);
          if (fileInput) fileInput.files = dataTransfer.files;
        } catch (_) {}
        handleFileSelection(files[0]);
      }
    });
  }

  fileInput?.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileSelection(e.target.files[0]);
    }
  });

  function handleFileSelection(file) {
    if (!file) return;

    if (file.size > MAX_FILE_SIZE) {
      showToast('danger', `File size (${formatBytes(file.size)}) exceeds the 50MB limit.`);
      clearSelectedFile();
      return;
    }

    if (selectedFileName) selectedFileName.textContent = file.name;
    if (selectedFileSize) selectedFileSize.textContent = formatBytes(file.size);
    selectedFileInfo?.classList.remove('d-none');
    if (fileSubmitBtn) fileSubmitBtn.disabled = false;
    if (dropText) dropText.textContent = 'File ready to upload';
  }

  function clearSelectedFile() {
    if (fileInput) fileInput.value = '';
    selectedFileInfo?.classList.add('d-none');
    if (fileSubmitBtn) fileSubmitBtn.disabled = true;
    if (dropText) dropText.textContent = 'Click or drag file here';
  }

  clearFileBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    clearSelectedFile();
  });

  // ==========================================================================
  // 5. Upload Pipeline with Progress Bar & Spinners (Feature 17)
  // ==========================================================================
  const progressSection = document.getElementById('uploadProgressSection');
  const progressBar = document.getElementById('uploadProgressBar');
  const statusText = document.getElementById('uploadStatusText');
  const percentText = document.getElementById('uploadPercentText');
  const bytesText = document.getElementById('uploadBytesText');
  const speedText = document.getElementById('uploadSpeedText');
  const fileUploadForm = document.getElementById('fileUploadForm');
  const urlUploadForm = document.getElementById('urlUploadForm');
  const urlSubmitBtn = document.getElementById('urlSubmitBtn');

  function executeUpload(formData, submitBtn, btnText, isUrlImport = false) {
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> ${isUrlImport ? 'Fetching...' : 'Uploading...'}`;
    }

    progressSection?.classList.remove('d-none');
    if (progressBar) progressBar.value = 0;
    if (percentText) percentText.textContent = isUrlImport ? 'Fetching...' : '0%';
    if (statusText) {
      statusText.innerHTML = isUrlImport
        ? '<i class="bi bi-globe me-1" aria-hidden="true"></i> Requesting remote URL...'
        : '<i class="bi bi-arrow-up-circle me-1" aria-hidden="true"></i> Uploading...';
    }
    if (bytesText) bytesText.textContent = '';
    if (speedText) speedText.textContent = '';

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/upload', true);
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');

    const startTime = Date.now();

    xhr.upload.onprogress = (e) => {
      if (!isUrlImport && e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 100);
        if (progressBar) progressBar.value = percent;
        if (percentText) percentText.textContent = `${percent}%`;
        if (bytesText) bytesText.textContent = `${formatBytes(e.loaded)} / ${formatBytes(e.total)}`;

        const elapsed = (Date.now() - startTime) / 1000;
        if (elapsed > 0.4) {
          const speed = e.loaded / elapsed;
          if (speedText) speedText.textContent = `${formatBytes(speed)}/s`;
        }

        if (percent === 100 && statusText) {
          statusText.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> Committing to GitHub storage...';
        }
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 400) {
        let msg = 'Upload successful!';
        try {
          const res = JSON.parse(xhr.responseText);
          if (res.message) msg = res.message;
        } catch (_) {}

        showToast('success', msg);
        setTimeout(() => location.reload(), 600);
      } else {
        let errorMsg = 'Upload failed.';
        try {
          const res = JSON.parse(xhr.responseText);
          if (res.error) errorMsg = res.error;
        } catch (_) {
          if (xhr.status === 413) errorMsg = 'File exceeds maximum upload size (50MB).';
          else if (xhr.status === 403) errorMsg = 'Vault is locked or access denied.';
        }
        showToast('danger', errorMsg);
        resetUploadState(submitBtn, btnText);
      }
    };

    xhr.onerror = () => {
      showToast('danger', 'Network error occurred during upload.');
      resetUploadState(submitBtn, btnText);
    };

    xhr.ontimeout = () => {
      showToast('danger', 'Upload timed out. Please check your network.');
      resetUploadState(submitBtn, btnText);
    };

    xhr.send(formData);
  }

  function resetUploadState(submitBtn, btnText) {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = btnText;
    }
    progressSection?.classList.add('d-none');
  }

  fileUploadForm?.addEventListener('submit', (e) => {
    e.preventDefault();
    if (!fileInput?.files?.[0]) return;
    const formData = new FormData(fileUploadForm);
    executeUpload(formData, fileSubmitBtn, '<i class="bi bi-cloud-upload me-1" aria-hidden="true"></i> Upload to Cloud', false);
  });

  urlUploadForm?.addEventListener('submit', (e) => {
    e.preventDefault();
    const urlInput = document.getElementById('urlInput');
    if (!urlInput?.value) return;
    const formData = new FormData(urlUploadForm);
    executeUpload(formData, urlSubmitBtn, '<i class="bi bi-cloud-download me-1" aria-hidden="true"></i> Fetch & Import', true);
  });

  // ==========================================================================
  // 6. Safe Deletion & Native Modal (Feature 14)
  // ==========================================================================
  const deleteModal = document.getElementById('deleteModal');
  const deleteTargetName = document.getElementById('deleteTargetName');
  const deleteFolderNotice = document.getElementById('deleteFolderNotice');
  const cancelDeleteBtn = document.getElementById('cancelDeleteBtn');
  const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');

  let activeDeleteTarget = null; // { path, isFolder, name }

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-delete');
    if (!btn) return;

    const path = btn.dataset.path || '';
    const isFolder = btn.dataset.type === 'folder';
    const name = btn.dataset.name || path.split('/').pop();

    activeDeleteTarget = { path, isFolder, name };

    if (deleteTargetName) deleteTargetName.textContent = name;
    if (deleteFolderNotice) {
      deleteFolderNotice.classList.toggle('d-none', !isFolder);
    }

    if (confirmDeleteBtn) {
      confirmDeleteBtn.disabled = false;
      confirmDeleteBtn.innerHTML = '<i class="bi bi-trash3-fill me-1" aria-hidden="true"></i> Delete Permanently';
    }

    deleteModal?.showModal();
    cancelDeleteBtn?.focus(); // Safe default focus
  });

  cancelDeleteBtn?.addEventListener('click', () => deleteModal?.close());

  // Click on modal backdrop closes modal
  deleteModal?.addEventListener('click', (e) => {
    const rect = deleteModal.getBoundingClientRect();
    const isInDialog = (
      rect.top <= e.clientY && e.clientY <= rect.top + rect.height &&
      rect.left <= e.clientX && e.clientX <= rect.left + rect.width
    );
    if (!isInDialog) deleteModal.close();
  });

  confirmDeleteBtn?.addEventListener('click', async () => {
    if (!activeDeleteTarget) return;
    const { path, isFolder, name } = activeDeleteTarget;

    confirmDeleteBtn.disabled = true;
    confirmDeleteBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> Deleting...';

    const safePath = path.split('/').map(encodeURIComponent).join('/');
    const endpoint = isFolder ? `/api/folders/${safePath}` : `/api/files/${safePath}`;

    try {
      const res = await fetch(endpoint, {
        method: 'DELETE',
        headers: { 'Accept': 'application/json' }
      });

      if (res.ok) {
        deleteModal.close();
        showToast('success', `${isFolder ? 'Folder' : 'File'} '${name}' deleted successfully.`);
        setTimeout(() => location.reload(), 400);
      } else {
        const data = await res.json().catch(() => ({}));
        showToast('danger', data.error || 'Failed to delete resource.');
        confirmDeleteBtn.disabled = false;
        confirmDeleteBtn.innerHTML = '<i class="bi bi-trash3-fill me-1" aria-hidden="true"></i> Delete Permanently';
      }
    } catch (_) {
      showToast('danger', 'Network error during deletion.');
      confirmDeleteBtn.disabled = false;
      confirmDeleteBtn.innerHTML = '<i class="bi bi-trash3-fill me-1" aria-hidden="true"></i> Delete Permanently';
    }
  });

  // ==========================================================================
  // 6b. Move to Private Vault & Native Modal
  // ==========================================================================
  const moveToVaultModal = document.getElementById('moveToVaultModal');
  const moveVaultTargetName = document.getElementById('moveVaultTargetName');
  const moveVaultFolderNotice = document.getElementById('moveVaultFolderNotice');
  const cancelMoveVaultBtn = document.getElementById('cancelMoveVaultBtn');
  const confirmMoveVaultBtn = document.getElementById('confirmMoveVaultBtn');

  let activeMoveTarget = null; // { path, isFolder, name }

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-move-vault');
    if (!btn) return;

    const path = btn.dataset.path || '';
    const isFolder = btn.dataset.type === 'folder';
    const name = btn.dataset.name || path.split('/').pop();

    activeMoveTarget = { path, isFolder, name };

    if (moveVaultTargetName) moveVaultTargetName.textContent = name;
    if (moveVaultFolderNotice) {
      moveVaultFolderNotice.classList.toggle('d-none', !isFolder);
    }

    if (confirmMoveVaultBtn) {
      confirmMoveVaultBtn.disabled = false;
      confirmMoveVaultBtn.innerHTML = '<i class="bi bi-shield-lock-fill me-1" aria-hidden="true"></i> Move to Vault';
    }

    moveToVaultModal?.showModal();
    cancelMoveVaultBtn?.focus();
  });

  cancelMoveVaultBtn?.addEventListener('click', () => moveToVaultModal?.close());

  moveToVaultModal?.addEventListener('click', (e) => {
    const rect = moveToVaultModal.getBoundingClientRect();
    const isInDialog = (
      rect.top <= e.clientY && e.clientY <= rect.top + rect.height &&
      rect.left <= e.clientX && e.clientX <= rect.left + rect.width
    );
    if (!isInDialog) moveToVaultModal.close();
  });

  confirmMoveVaultBtn?.addEventListener('click', async () => {
    if (!activeMoveTarget) return;
    const { path, isFolder, name } = activeMoveTarget;

    confirmMoveVaultBtn.disabled = true;
    confirmMoveVaultBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> Moving to Vault...';

    try {
      const res = await fetch('/api/vault/move', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({ path })
      });

      if (res.ok) {
        moveToVaultModal?.close();
        showToast('success', `'${name}' moved to Private Vault successfully! 🔐`);
        setTimeout(() => location.reload(), 400);
      } else {
        const data = await res.json().catch(() => ({}));
        showToast('danger', data.error || 'Failed to move item to vault.');
        confirmMoveVaultBtn.disabled = false;
        confirmMoveVaultBtn.innerHTML = '<i class="bi bi-shield-lock-fill me-1" aria-hidden="true"></i> Move to Vault';
      }
    } catch (_) {
      showToast('danger', 'Network error while moving to vault.');
      confirmMoveVaultBtn.disabled = false;
      confirmMoveVaultBtn.innerHTML = '<i class="bi bi-shield-lock-fill me-1" aria-hidden="true"></i> Move to Vault';
    }
  });

  // ==========================================================================
  // 7. New Folder Modal Dialog
  // ==========================================================================
  const newFolderModal = document.getElementById('newFolderModal');
  const btnOpenFolderModal = document.getElementById('btnOpenFolderModal');
  const cancelFolderBtn = document.getElementById('cancelFolderBtn');
  const newFolderNameInput = document.getElementById('newFolderNameInput');

  btnOpenFolderModal?.addEventListener('click', () => {
    if (newFolderNameInput) newFolderNameInput.value = '';
    newFolderModal?.showModal();
    newFolderNameInput?.focus();
  });

  cancelFolderBtn?.addEventListener('click', () => newFolderModal?.close());

  newFolderModal?.addEventListener('click', (e) => {
    const rect = newFolderModal.getBoundingClientRect();
    const isInDialog = (
      rect.top <= e.clientY && e.clientY <= rect.top + rect.height &&
      rect.left <= e.clientX && e.clientX <= rect.left + rect.width
    );
    if (!isInDialog) newFolderModal.close();
  });

  // ==========================================================================
  // 8. In-App File Preview Modal (Feature 16)
  // ==========================================================================
  const previewModal = document.getElementById('previewModal');
  const previewFileName = document.getElementById('previewFileName');
  const previewFileSize = document.getElementById('previewFileSize');
  const previewMimeType = document.getElementById('previewMimeType');
  const previewDownloadLink = document.getElementById('previewDownloadLink');
  const closePreviewBtn = document.getElementById('closePreviewBtn');

  const previewLoadingState = document.getElementById('previewLoadingState');
  const previewImagePane = document.getElementById('previewImagePane');
  const previewImg = document.getElementById('previewImg');
  const previewPdfPane = document.getElementById('previewPdfPane');
  const previewPdfFrame = document.getElementById('previewPdfFrame');
  const previewTextPane = document.getElementById('previewTextPane');
  const previewCodeContent = document.getElementById('previewCodeContent');
  const previewFallbackPane = document.getElementById('previewFallbackPane');
  const previewFallbackDownloadBtn = document.getElementById('previewFallbackDownloadBtn');

  let activePreviewBlobUrl = null;
  const MAX_PREVIEW_SIZE = 10 * 1024 * 1024; // 10MB limit

  function parseSizeToBytes(sizeStr) {
    if (!sizeStr || typeof sizeStr !== 'string') return 0;
    const match = sizeStr.trim().match(/^([\d.]+)\s*([a-zA-Z]+)?$/);
    if (!match) return 0;
    const val = parseFloat(match[1]);
    if (isNaN(val)) return 0;
    const unit = (match[2] || 'B').toUpperCase();
    const multipliers = {
      B: 1,
      KB: 1024,
      MB: 1024 * 1024,
      GB: 1024 * 1024 * 1024,
      TB: 1024 * 1024 * 1024 * 1024,
    };
    return Math.round(val * (multipliers[unit] || 1));
  }

  function cleanupPreview() {
    [previewLoadingState, previewImagePane, previewPdfPane, previewTextPane, previewFallbackPane].forEach(p => {
      p?.classList.add('d-none');
    });
    if (activePreviewBlobUrl) {
      URL.revokeObjectURL(activePreviewBlobUrl);
      activePreviewBlobUrl = null;
    }
    if (previewImg) previewImg.src = '';
    if (previewPdfFrame) previewPdfFrame.src = '';
    if (previewCodeContent) previewCodeContent.textContent = '';

    const fallbackMsg = previewFallbackPane?.querySelector('p');
    if (fallbackMsg) {
      fallbackMsg.textContent = 'This binary file format cannot be viewed directly inside the browser.';
    }
  }

  // Alias resetPreviewPanes for backward compatibility
  const resetPreviewPanes = cleanupPreview;

  function closePreview() {
    cleanupPreview();
    previewModal?.close();
  }

  closePreviewBtn?.addEventListener('click', closePreview);

  // Guarantee cleanup on native Escape key or any modal dismissal
  previewModal?.addEventListener('close', cleanupPreview);
  previewModal?.addEventListener('cancel', cleanupPreview);

  previewModal?.addEventListener('click', (e) => {
    const rect = previewModal.getBoundingClientRect();
    const isInDialog = (
      rect.top <= e.clientY && e.clientY <= rect.top + rect.height &&
      rect.left <= e.clientX && e.clientX <= rect.left + rect.width
    );
    if (!isInDialog) closePreview();
  });

  document.addEventListener('click', async (e) => {
    const trigger = e.target.closest('.btn-preview, .file-name-preview');
    if (!trigger) return;
    e.preventDefault();

    const path = trigger.dataset.path || '';
    const name = trigger.dataset.name || path.split('/').pop();
    const mime = trigger.dataset.mime || '';
    const size = trigger.dataset.size || '';
    const displayPath = path.startsWith('storage/') ? path.slice(8) : path;
    const streamUrl = `/download/${displayPath.split('/').map(encodeURIComponent).join('/')}`;

    // 1. Determine file size in bytes
    const rawBytesAttr = trigger.dataset.bytes || trigger.closest('.file-item')?.dataset?.bytes;
    let fileSizeBytes = rawBytesAttr ? parseInt(rawBytesAttr, 10) : 0;
    if (!fileSizeBytes && size) {
      fileSizeBytes = parseSizeToBytes(size);
    }

    // 2. Populate header metadata
    if (previewFileName) previewFileName.textContent = name;
    if (previewFileSize) previewFileSize.textContent = size;
    if (previewMimeType) previewMimeType.textContent = mime || 'file';
    if (previewDownloadLink) previewDownloadLink.href = streamUrl;
    if (previewFallbackDownloadBtn) previewFallbackDownloadBtn.href = streamUrl;

    cleanupPreview();

    // 3. File size cap (>10MB)
    if (fileSizeBytes > MAX_PREVIEW_SIZE) {
      const fallbackMsg = previewFallbackPane?.querySelector('p');
      if (fallbackMsg) {
        fallbackMsg.textContent = 'File is too large for in-browser preview (>10MB). Please use direct download.';
      }
      previewFallbackPane?.classList.remove('d-none');
      previewModal?.showModal();
      return;
    }

    previewLoadingState?.classList.remove('d-none');
    previewModal?.showModal();

    const ext = getFileExtension(name);
    const isImage = mime.startsWith('image/') || ['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'bmp', 'ico'].includes(ext);
    const isPdf = mime === 'application/pdf' || ext === 'pdf';
    const isText = mime.startsWith('text/') || ['txt', 'md', 'py', 'js', 'json', 'html', 'css', 'yml', 'yaml', 'xml', 'sh', 'sql', 'csv', 'log', 'env'].includes(ext);

    try {
      const res = await fetch(streamUrl);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      // Secondary size check from Content-Length header
      const contentLengthHeader = res.headers.get('Content-Length');
      if (contentLengthHeader && parseInt(contentLengthHeader, 10) > MAX_PREVIEW_SIZE) {
        previewLoadingState?.classList.add('d-none');
        const fallbackMsg = previewFallbackPane?.querySelector('p');
        if (fallbackMsg) {
          fallbackMsg.textContent = 'File is too large for in-browser preview (>10MB). Please use direct download.';
        }
        previewFallbackPane?.classList.remove('d-none');
        return;
      }

      if (previewModal && !previewModal.open) return;

      const blob = await res.blob();
      if (previewModal && !previewModal.open) return;

      activePreviewBlobUrl = URL.createObjectURL(blob);

      previewLoadingState?.classList.add('d-none');

      if (isImage) {
        if (previewImg) previewImg.src = activePreviewBlobUrl;
        previewImagePane?.classList.remove('d-none');
      } else if (isPdf) {
        if (previewPdfFrame) previewPdfFrame.src = activePreviewBlobUrl;
        previewPdfPane?.classList.remove('d-none');
      } else if (isText) {
        const text = await blob.text();
        if (previewCodeContent) previewCodeContent.textContent = text;
        previewTextPane?.classList.remove('d-none');
      } else {
        previewFallbackPane?.classList.remove('d-none');
      }
    } catch (_) {
      previewLoadingState?.classList.add('d-none');
      previewFallbackPane?.classList.remove('d-none');
      showToast('warning', 'Unable to render inline preview. Please download the file to view.');
    }
  });

  // ==========================================================================
  // 9. Client-Side Sorting, Filtering & Search Engine (Features 19, 20)
  // ==========================================================================
  class FileExplorerEngine {
    constructor() {
      this.fileList = document.getElementById('file-list');
      this.searchInput = document.getElementById('searchInput');
      this.searchClearBtn = document.getElementById('searchClearBtn');
      this.kbdBadge = document.getElementById('search-kbd-badge');
      this.sortSelect = document.getElementById('sortSelect');
      this.filterPills = document.querySelectorAll('.filter-bar .filter-pill');
      this.emptySearchState = document.getElementById('search-empty-state');
      this.searchTermDisplay = document.getElementById('search-term-display');
      this.fileCountDisplay = document.getElementById('file-count');
      this.totalSizeDisplay = document.getElementById('total-size');

      this.currentCategory = 'all';
      this.searchTerm = '';
      this.currentSort = 'name-asc';

      this.init();
    }

    init() {
      if (!this.fileList) return;

      this.bindEvents();
      this.calculateCategoryCounts();
      this.applyFiltersAndSort();
    }

    bindEvents() {
      // Category Filter Pills
      this.filterPills.forEach(pill => {
        pill.addEventListener('click', () => {
          this.filterPills.forEach(p => {
            p.classList.remove('active');
            p.setAttribute('aria-selected', 'false');
          });
          pill.classList.add('active');
          pill.setAttribute('aria-selected', 'true');
          this.currentCategory = pill.dataset.filter || 'all';
          this.applyFiltersAndSort();
        });
      });

      // Sort Dropdown
      this.sortSelect?.addEventListener('change', (e) => {
        this.currentSort = e.target.value;
        this.sortItems();
      });

      // Real-time search
      this.searchInput?.addEventListener('input', (e) => {
        const term = e.target.value.trim().toLowerCase();
        this.searchTerm = term;

        if (term.length > 0) {
          this.searchClearBtn?.classList.remove('d-none');
          this.kbdBadge?.classList.add('d-none');
        } else {
          this.searchClearBtn?.classList.add('d-none');
          this.kbdBadge?.classList.remove('d-none');
        }

        this.applyFiltersAndSort();
      });

      // Search clear button
      this.searchClearBtn?.addEventListener('click', () => {
        if (this.searchInput) this.searchInput.value = '';
        this.searchTerm = '';
        this.searchClearBtn.classList.add('d-none');
        this.kbdBadge?.classList.remove('d-none');
        this.applyFiltersAndSort();
        this.searchInput?.focus();
      });

      // Reset button on empty state
      document.getElementById('btnResetSearch')?.addEventListener('click', () => {
        this.resetFilters();
      });

      // Global keyboard shortcut: '/' focuses search input
      window.addEventListener('keydown', (e) => {
        const tag = document.activeElement ? document.activeElement.tagName.toUpperCase() : '';
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || document.activeElement?.isContentEditable) {
          if (e.key === 'Escape' && document.activeElement === this.searchInput) {
            if (this.searchInput.value) {
              this.searchInput.value = '';
              this.searchTerm = '';
              this.searchClearBtn?.classList.add('d-none');
              this.kbdBadge?.classList.remove('d-none');
              this.applyFiltersAndSort();
            } else {
              this.searchInput.blur();
            }
          }
          return;
        }

        if (e.key === '/' || e.code === 'Slash') {
          e.preventDefault();
          this.searchInput?.focus();
          this.searchInput?.select();
        }
      });
    }

    calculateCategoryCounts() {
      const items = this.fileList.querySelectorAll('.file-item');
      const counts = { all: items.length, folder: 0, document: 0, image: 0, media: 0 };

      items.forEach(item => {
        const cat = item.dataset.category;
        if (counts[cat] !== undefined) {
          counts[cat]++;
        }
      });

      for (const [key, count] of Object.entries(counts)) {
        const badge = document.getElementById(`badge-${key}`);
        if (badge) badge.textContent = count;
      }
    }

    applyFiltersAndSort() {
      const items = this.fileList.querySelectorAll('.file-item');
      let visibleCount = 0;
      let totalBytes = 0;

      items.forEach(item => {
        const name = (item.dataset.name || '').toLowerCase();
        const cat = item.dataset.category || 'other';
        const bytes = parseInt(item.dataset.bytes || '0', 10);

        const matchesSearch = !this.searchTerm || name.includes(this.searchTerm);
        const matchesCategory = this.currentCategory === 'all' || cat === this.currentCategory;

        if (matchesSearch && matchesCategory) {
          item.style.display = '';
          visibleCount++;
          totalBytes += bytes;
        } else {
          item.style.display = 'none';
        }
      });

      // Update statistics
      if (this.fileCountDisplay) this.fileCountDisplay.textContent = visibleCount;
      if (this.totalSizeDisplay) this.totalSizeDisplay.textContent = formatBytes(totalBytes);

      // Handle Empty State
      if (this.emptySearchState) {
        if (visibleCount === 0 && items.length > 0) {
          this.emptySearchState.classList.remove('d-none');
          if (this.searchTermDisplay) {
            this.searchTermDisplay.textContent = this.searchTerm || this.currentCategory;
          }
        } else {
          this.emptySearchState.classList.add('d-none');
        }
      }

      this.sortItems();
    }

    sortItems() {
      const items = Array.from(this.fileList.querySelectorAll('.file-item'));
      if (!items.length) return;

      items.sort((a, b) => {
        const isDirA = a.dataset.isDir === 'true';
        const isDirB = b.dataset.isDir === 'true';

        // Folders always sorted first
        if (isDirA !== isDirB) {
          return isDirA ? -1 : 1;
        }

        const nameA = a.dataset.name || '';
        const nameB = b.dataset.name || '';
        const sizeA = parseInt(a.dataset.bytes || '0', 10);
        const sizeB = parseInt(b.dataset.bytes || '0', 10);

        switch (this.currentSort) {
          case 'name-asc':
            return nameA.localeCompare(nameB, undefined, { numeric: true, sensitivity: 'base' });
          case 'name-desc':
            return nameB.localeCompare(nameA, undefined, { numeric: true, sensitivity: 'base' });
          case 'size-desc':
            return sizeB - sizeA;
          case 'size-asc':
            return sizeA - sizeB;
          case 'type-asc': {
            const catA = a.dataset.category || '';
            const catB = b.dataset.category || '';
            if (catA !== catB) return catA.localeCompare(catB);
            return nameA.localeCompare(nameB);
          }
          default:
            return 0;
        }
      });

      // Re-attach in sorted order without DOM destruction
      items.forEach(item => this.fileList.appendChild(item));
    }

    resetFilters() {
      if (this.searchInput) {
        this.searchInput.value = '';
        this.searchTerm = '';
      }
      this.searchClearBtn?.classList.add('d-none');
      this.kbdBadge?.classList.remove('d-none');

      this.filterPills.forEach(p => {
        const isAll = p.dataset.filter === 'all';
        p.classList.toggle('active', isAll);
        p.setAttribute('aria-selected', isAll ? 'true' : 'false');
      });
      this.currentCategory = 'all';

      this.applyFiltersAndSort();
      this.searchInput?.focus();
    }
  }

  // Instantiate file explorer engine
  new FileExplorerEngine();
});

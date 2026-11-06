// upload.js - Interactive Upload & Batch Review controller
import { api } from './api.js';

let metaData = null;
let currentJobId = null;
let pollTimer = null;
let currentPage = 1;
const pageSize = 10;
let totalPages = 1;
let totalRows = 0;
let lastStatus = null;
const editedRowIds = new Set();

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function parseApiError(err) {
  if (!err) return 'An unexpected error occurred.';
  if (err.error && err.error.message) return err.error.message;
  if (err.detail) {
    if (typeof err.detail === 'string') return err.detail;
    if (Array.isArray(err.detail)) {
      return err.detail.map(d => d.msg || JSON.stringify(d)).join('; ');
    }
  }
  if (err.message) return err.message;
  if (typeof err === 'string') return err;
  return 'Validation failed. Please verify that your CSV/XLSX matches the required columns.';
}

function showError(message) {
  const errorCard = document.getElementById('errorCard');
  const errorMsg = document.getElementById('errorMessage');
  if (errorCard && errorMsg) {
    if (typeof message === 'string' && (message.toLowerCase().includes('expired') || message.toLowerCase().includes('restarted'))) {
      errorMsg.innerHTML = `${escapeHtml(message)}<div class="mt-2"><a href="/upload" class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary text-on-primary rounded text-xs font-semibold hover:opacity-90">Start Fresh Upload</a></div>`;
    } else {
      errorMsg.textContent = message;
    }
    errorCard.classList.remove('hidden');
    errorCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

function hideError() {
  const errorCard = document.getElementById('errorCard');
  if (errorCard) {
    errorCard.classList.add('hidden');
  }
}

function updateStatusUI(status) {
  const emptyStateCard = document.getElementById('emptyStateCard');
  const processingCard = document.getElementById('processingCard');
  const previewCard = document.getElementById('previewCard');
  const bottomBar = document.getElementById('bottomSummaryBar');
  const fallbackBanner = document.getElementById('fallbackBanner');
  const fallbackText = document.getElementById('fallbackText');
  const aiUnavailableNotice = document.getElementById('aiUnavailableNotice');

  if (emptyStateCard) emptyStateCard.classList.add('hidden');
  if (processingCard) processingCard.classList.remove('hidden');
  if (previewCard) previewCard.classList.remove('hidden');
  if (bottomBar) bottomBar.classList.remove('hidden');

  const statusTitle = document.getElementById('statusTitle');
  const statusBadge = document.getElementById('statusBadge');
  const statusDetail = document.getElementById('statusDetail');
  const progressBar = document.getElementById('progressBar');
  const statusSpinner = document.getElementById('statusSpinner');

  const tagged = status.rows_tagged || 0;
  const total = status.total || 0;
  const pct = total > 0 ? Math.round((tagged / total) * 100) : 0;

  if (progressBar) {
    progressBar.style.width = `${pct}%`;
  }

  if (status.state === 'running') {
    if (statusSpinner) {
      statusSpinner.textContent = 'sync';
      statusSpinner.classList.add('animate-spin');
      statusSpinner.className = 'material-symbols-outlined text-primary text-[22px] animate-spin';
    }
    if (statusTitle) statusTitle.textContent = `AI is tagging ${tagged} of ${total} rows...`;
    if (statusBadge) {
      statusBadge.textContent = `${pct}% Complete`;
      statusBadge.className = 'px-2.5 py-0.5 rounded-full bg-primary-fixed text-on-primary-fixed text-xs font-semibold';
    }
    if (statusDetail) statusDetail.textContent = `${total - tagged} rows remaining`;
  } else if (status.state === 'done') {
    if (statusSpinner) {
      statusSpinner.textContent = 'check_circle';
      statusSpinner.classList.remove('animate-spin');
      statusSpinner.className = 'material-symbols-outlined text-primary text-[22px]';
    }
    if (statusTitle) statusTitle.textContent = `Tagging complete (${tagged} rows processed)`;
    if (statusBadge) {
      statusBadge.textContent = 'Done';
      statusBadge.className = 'px-2.5 py-0.5 rounded-full bg-primary text-on-primary text-xs font-semibold';
    }
    if (statusDetail) statusDetail.textContent = 'All rows classified';
  } else if (status.state === 'failed') {
    if (statusSpinner) {
      statusSpinner.textContent = 'error';
      statusSpinner.classList.remove('animate-spin');
      statusSpinner.className = 'material-symbols-outlined text-error text-[22px]';
    }
    if (statusTitle) statusTitle.textContent = 'Tagging failed';
    if (statusBadge) {
      statusBadge.textContent = 'Failed';
      statusBadge.className = 'px-2.5 py-0.5 rounded-full bg-error-container text-on-error-container text-xs font-semibold';
    }
    if (statusDetail) statusDetail.textContent = status.error_message || 'Processing error';
  }

  // Fallback Notice Handling
  const fallbacks = status.fallback_count || 0;
  if (fallbackBanner && fallbackText) {
    if (fallbacks > 0) {
      fallbackText.textContent = `Notice: ${fallbacks} row(s) used fallback classifications (Other / Unknown / Unclear) because AI was unavailable or low confidence. You can review and adjust them below.`;
      fallbackBanner.classList.remove('hidden');
    } else {
      fallbackBanner.classList.add('hidden');
    }
  }

  // Data Warnings / Missing Columns Notice Handling
  const dataNoticeBanner = document.getElementById('dataNoticeBanner');
  const dataNoticeText = document.getElementById('dataNoticeText');
  const warnings = status.data_warnings || [];
  if (dataNoticeBanner && dataNoticeText) {
    if (warnings.length > 0) {
      dataNoticeText.innerHTML = warnings.map(w => escapeHtml(w)).join('<br/>') + '<br/><span class="text-blue-900 font-semibold mt-1 inline-block">All available feedback text was accepted and classified successfully.</span>';
      dataNoticeBanner.classList.remove('hidden');
    } else {
      dataNoticeBanner.classList.add('hidden');
    }
  }

  // AI Unavailability Notice
  if (aiUnavailableNotice && metaData && metaData.ai_available === false) {
    aiUnavailableNotice.classList.remove('hidden');
  }

  // Bottom Summary Bar update
  const summaryTotalTagged = document.getElementById('summaryTotalTagged');
  const summaryFallbackCount = document.getElementById('summaryFallbackCount');
  const summaryEditedCount = document.getElementById('summaryEditedCount');
  const btnExportJobCsv = document.getElementById('btnExportJobCsv');
  const btnViewInsights = document.getElementById('btnViewInsights');

  if (summaryTotalTagged) summaryTotalTagged.textContent = `${tagged} of ${total}`;
  if (summaryFallbackCount) summaryFallbackCount.textContent = fallbacks;
  if (summaryEditedCount) summaryEditedCount.textContent = editedRowIds.size;

  if (btnExportJobCsv) {
    if (tagged > 0 || status.state === 'done') {
      btnExportJobCsv.href = `/api/upload/${encodeURIComponent(status.job_id)}/export.csv`;
      btnExportJobCsv.setAttribute('download', `job_${status.job_id}_export.csv`);
      btnExportJobCsv.classList.remove('opacity-50', 'pointer-events-none');
    } else {
      btnExportJobCsv.classList.add('opacity-50', 'pointer-events-none');
    }
  }

  if (btnViewInsights) {
    if (tagged > 0 || status.state === 'done') {
      btnViewInsights.href = `/insights?dataset=${encodeURIComponent(status.job_id)}`;
      btnViewInsights.classList.remove('opacity-50', 'pointer-events-none');
    } else {
      btnViewInsights.classList.add('opacity-50', 'pointer-events-none');
    }
  }
}

function updatePaginationUI(page, pages, total) {
  const pageIndicator = document.getElementById('paginationIndicator');
  const btnPrev = document.getElementById('btnPrevPage');
  const btnNext = document.getElementById('btnNextPage');
  const previewCountBadge = document.getElementById('previewCountBadge');

  if (pageIndicator) {
    pageIndicator.textContent = `Page ${page} of ${pages || 1} (${total} total rows)`;
  }
  if (previewCountBadge) {
    previewCountBadge.textContent = `${total} Total Rows`;
  }
  if (btnPrev) {
    btnPrev.disabled = page <= 1;
  }
  if (btnNext) {
    btnNext.disabled = page >= pages;
  }
}

function renderTableRows(items) {
  const tbody = document.getElementById('previewTableBody');
  if (!tbody) return;

  if (!items || items.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="py-8 px-4 text-center text-on-surface-variant font-medium">
          No records tagged yet. Tagging in progress...
        </td>
      </tr>
    `;
    return;
  }

  const allowedStages = (metaData && (metaData.stage || (metaData.allowed_values && metaData.allowed_values.stage))) || [];
  const allowedDrivers = (metaData && (metaData.main_driver || (metaData.allowed_values && metaData.main_driver))) || [];
  const allowedOutcomes = (metaData && (metaData.outcome || (metaData.allowed_values && metaData.outcome))) || [];

  const html = items.map(item => {
    const isFallback = item.label_origin === 'fallback';
    const isEdited = editedRowIds.has(item.id);

    // Build Stage Select Options
    const stageOptions = allowedStages.map(s => {
      const sel = s === item.stage ? 'selected' : '';
      return `<option value="${escapeHtml(s)}" ${sel}>${escapeHtml(s)}</option>`;
    }).join('');

    // Build Driver Select Options
    const driverOptions = allowedDrivers.map(d => {
      const sel = d === item.main_driver ? 'selected' : '';
      return `<option value="${escapeHtml(d)}" ${sel}>${escapeHtml(d)}</option>`;
    }).join('');

    // Build Outcome Select Options
    const outcomeOptions = allowedOutcomes.map(o => {
      const sel = o === item.outcome ? 'selected' : '';
      return `<option value="${escapeHtml(o)}" ${sel}>${escapeHtml(o)}</option>`;
    }).join('');

    const sourceBadge = `<span class="px-2 py-0.5 rounded-full bg-surface-container-high text-on-surface text-[11px] font-medium uppercase tracking-wider">${escapeHtml(item.source)}</span>`;

    return `
      <tr class="hover:bg-surface-container-low/60 transition-colors border-b border-outline-variant/15" data-row-id="${escapeHtml(item.id)}">
        <td class="py-3 px-3 font-mono font-semibold text-on-surface text-xs truncate max-w-[100px]" title="${escapeHtml(item.id)}">
          ${escapeHtml(item.id)}
          ${isEdited ? '<span class="ml-1 inline-block w-1.5 h-1.5 rounded-full bg-emerald-500" title="User edited"></span>' : ''}
          ${isFallback && !isEdited ? '<span class="ml-1 inline-block w-1.5 h-1.5 rounded-full bg-amber-500" title="Fallback label"></span>' : ''}
        </td>
        <td class="py-3 px-3">
          ${sourceBadge}
        </td>
        <td class="py-3 px-3">
          <p class="truncate text-on-surface max-w-[220px]" title="${escapeHtml(item.text)}">
            "${escapeHtml(item.text)}"
          </p>
        </td>
        <td class="py-3 px-3">
          <select 
            data-row-id="${escapeHtml(item.id)}" 
            data-field="stage"
            class="row-select w-full text-xs py-1 px-2 rounded-lg bg-surface-container border border-outline-variant/40 focus:border-primary focus:ring-1 focus:ring-primary text-on-surface transition-all cursor-pointer truncate"
            title="Edit Journey Stage"
          >
            ${stageOptions}
          </select>
        </td>
        <td class="py-3 px-3">
          <select 
            data-row-id="${escapeHtml(item.id)}" 
            data-field="main_driver"
            class="row-select w-full text-xs py-1 px-2 rounded-lg bg-surface-container border border-outline-variant/40 focus:border-primary focus:ring-1 focus:ring-primary text-on-surface transition-all cursor-pointer truncate"
            title="Edit Main Driver"
          >
            ${driverOptions}
          </select>
        </td>
        <td class="py-3 px-3 text-right">
          <select 
            data-row-id="${escapeHtml(item.id)}" 
            data-field="outcome"
            class="row-select w-full text-xs py-1 px-2 rounded-lg bg-surface-container border border-outline-variant/40 focus:border-primary focus:ring-1 focus:ring-primary text-on-surface transition-all cursor-pointer truncate"
            title="Edit Outcome"
          >
            ${outcomeOptions}
          </select>
        </td>
      </tr>
    `;
  }).join('');

  tbody.innerHTML = html;

  // Attach change listeners to editable dropdowns
  tbody.querySelectorAll('.row-select').forEach(select => {
    select.addEventListener('change', handleLabelChange);
  });
}

async function handleLabelChange(e) {
  const select = e.target;
  const rowId = select.dataset.rowId;
  const field = select.dataset.field;
  const newValue = select.value;

  if (!currentJobId || !rowId || !field) return;

  select.disabled = true;
  select.classList.add('ring-2', 'ring-primary/40');

  try {
    const payload = {};
    payload[field] = newValue;
    await api.updateJobRow(currentJobId, rowId, payload);

    editedRowIds.add(rowId);

    // Visual feedback
    select.classList.remove('ring-primary/40');
    select.classList.add('ring-2', 'ring-emerald-500');

    const summaryEditedCount = document.getElementById('summaryEditedCount');
    if (summaryEditedCount) summaryEditedCount.textContent = editedRowIds.size;

    setTimeout(() => {
      select.classList.remove('ring-2', 'ring-emerald-500');
    }, 1000);
  } catch (err) {
    console.error('Failed to update label:', err);
    alert(`Failed to save change: ${parseApiError(err)}`);
    // Reload current page to reset value
    await loadJobRows(currentPage);
  } finally {
    select.disabled = false;
  }
}

async function loadJobRows(page = 1) {
  if (!currentJobId) return;
  try {
    const data = await api.getJobRows(currentJobId, page, pageSize);
    currentPage = data.page;
    totalPages = data.total_pages;
    totalRows = data.total;
    renderTableRows(data.items);
    updatePaginationUI(currentPage, totalPages, totalRows);
  } catch (err) {
    console.error('Error fetching job rows:', err);
  }
}

async function pollStatus() {
  if (!currentJobId) return;
  try {
    const status = await api.getJobStatus(currentJobId);
    lastStatus = status;
    updateStatusUI(status);
    await loadJobRows(currentPage);

    if (status.state === 'done') {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    } else if (status.state === 'failed') {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
      showError(status.error_message || 'Processing failed.');
    }
  } catch (err) {
    console.error('Polling error:', err);
    if (err && err.error && err.error.code === 'HTTP_404') {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
      showError('Uploaded job session was not found.');
    }
  }
}

function startPolling(jobId) {
  currentJobId = jobId;
  currentPage = 1;
  editedRowIds.clear();

  if (pollTimer) clearInterval(pollTimer);
  pollStatus();
  pollTimer = setInterval(pollStatus, 700);
}

async function handleFileUpload(file) {
  if (!file) return;
  hideError();

  // Instant local format check
  const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
  if (ext !== '.csv' && ext !== '.xlsx') {
    showError(`Unsupported file format "${ext}". Please upload a .csv or .xlsx file.`);
    return;
  }

  // Temporary uploading UI
  const emptyStateCard = document.getElementById('emptyStateCard');
  if (emptyStateCard) emptyStateCard.classList.add('hidden');
  const processingCard = document.getElementById('processingCard');
  if (processingCard) processingCard.classList.remove('hidden');

  const statusTitle = document.getElementById('statusTitle');
  if (statusTitle) statusTitle.textContent = `Uploading ${file.name}...`;

  try {
    const res = await api.uploadFile(file);
    startPolling(res.job_id);
  } catch (err) {
    showError(parseApiError(err));
    if (emptyStateCard) emptyStateCard.classList.remove('hidden');
    if (processingCard) processingCard.classList.add('hidden');
  }
}

async function handleSampleUpload() {
  hideError();

  const emptyStateCard = document.getElementById('emptyStateCard');
  if (emptyStateCard) emptyStateCard.classList.add('hidden');
  const processingCard = document.getElementById('processingCard');
  if (processingCard) processingCard.classList.remove('hidden');

  const statusTitle = document.getElementById('statusTitle');
  if (statusTitle) statusTitle.textContent = 'Loading sample_upload.csv...';

  try {
    const res = await api.uploadSample();
    startPolling(res.job_id);
  } catch (err) {
    showError(parseApiError(err));
    if (emptyStateCard) emptyStateCard.classList.remove('hidden');
    if (processingCard) processingCard.classList.add('hidden');
  }
}

export async function initUploadPage() {
  try {
    metaData = await api.getMeta();
  } catch (err) {
    console.error('Failed to load metadata:', err);
  }

  // Setup AI Unavailable banner if applicable
  const aiUnavailableNotice = document.getElementById('aiUnavailableNotice');
  if (aiUnavailableNotice && metaData && metaData.ai_available === false) {
    aiUnavailableNotice.classList.remove('hidden');
  }

  // File Upload Input
  const fileInput = document.getElementById('fileUploadInput');
  const dropZone = document.getElementById('dropZone');

  if (fileInput) {
    fileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        handleFileUpload(e.target.files[0]);
        // reset input so same file can be re-uploaded if needed
        fileInput.value = '';
      }
    });
  }

  // Drag and Drop
  if (dropZone) {
    ['dragenter', 'dragover'].forEach(eventName => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add('border-primary', 'bg-surface-container');
      });
    });

    ['dragleave', 'drop'].forEach(eventName => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove('border-primary', 'bg-surface-container');
      });
    });

    dropZone.addEventListener('drop', (e) => {
      const dt = e.dataTransfer;
      if (dt && dt.files && dt.files[0]) {
        handleFileUpload(dt.files[0]);
      }
    });
  }

  // Sample data button
  const btnSampleData = document.getElementById('btnSampleData');
  if (btnSampleData) {
    btnSampleData.addEventListener('click', () => {
      handleSampleUpload();
    });
  }

  // Dismiss Error button
  const btnDismissError = document.getElementById('btnDismissError');
  if (btnDismissError) {
    btnDismissError.addEventListener('click', () => {
      hideError();
    });
  }

  // Pagination Buttons
  const btnPrevPage = document.getElementById('btnPrevPage');
  if (btnPrevPage) {
    btnPrevPage.addEventListener('click', () => {
      if (currentPage > 1) {
        loadJobRows(currentPage - 1);
      }
    });
  }

  const btnNextPage = document.getElementById('btnNextPage');
  if (btnNextPage) {
    btnNextPage.addEventListener('click', () => {
      if (currentPage < totalPages) {
        loadJobRows(currentPage + 1);
      }
    });
  }

  // Check URL params for existing dataset/job_id
  const urlParams = new URLSearchParams(window.location.search);
  const existingJobId = urlParams.get('job_id') || urlParams.get('dataset');
  if (existingJobId) {
    startPolling(existingJobId);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initUploadPage();
});


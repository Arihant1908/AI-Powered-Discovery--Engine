// insights.js - AI Qualitative Insights & Segment View controller
import { api } from './api.js';

let currentDataset = 'preloaded';
let insightsData = null;

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
  return 'Failed to load insights.';
}

function getStrengthBadge(strength, count, label) {
  const safeCount = count !== undefined ? count : 0;
  const countStr = safeCount === 1 ? '1 item' : `${safeCount} items`;

  if (strength === 'Strong') {
    return `
      <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary-fixed text-on-primary-fixed font-semibold text-xs tracking-tight shadow-xs">
        <span class="material-symbols-outlined text-[15px]">verified</span>
        <span>Strong signal (${countStr})</span>
      </span>
    `;
  } else if (strength === 'Medium') {
    return `
      <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-secondary-fixed text-on-secondary-fixed font-semibold text-xs tracking-tight shadow-xs">
        <span class="material-symbols-outlined text-[15px]">tune</span>
        <span>Medium signal (${countStr})</span>
      </span>
    `;
  } else {
    return `
      <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-container-high text-on-surface-variant font-semibold text-xs tracking-tight shadow-xs">
        <span class="material-symbols-outlined text-[15px]">help_outline</span>
        <span>Weak signal (${countStr})</span>
      </span>
    `;
  }
}

function renderDataWarnings(warnings) {
  const banner = document.getElementById('dataNoticeBanner');
  const messageEl = document.getElementById('dataNoticeMessage');
  if (!banner || !messageEl) return;

  if (warnings && warnings.length > 0) {
    messageEl.innerHTML = warnings.map(w => `• ${escapeHtml(w)}`).join('<br/>') + '<br/><span class="font-medium text-on-surface mt-1 inline-block">Qualitative insight cards, driver analysis, and proposed PM actions below are synthesized from all available feedback records.</span>';
    banner.classList.remove('hidden');
  } else {
    banner.classList.add('hidden');
  }
}

function renderMetaRibbon(data) {
  const generatedTimeEl = document.getElementById('generatedTime');
  const datasetSummaryTextEl = document.getElementById('datasetSummaryText');
  const datasetBadgeEl = document.getElementById('datasetBadge');

  if (generatedTimeEl) {
    if (data.generated_at) {
      try {
        const d = new Date(data.generated_at);
        generatedTimeEl.textContent = `Generated at ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
      } catch (_) {
        generatedTimeEl.textContent = 'Generated just now';
      }
    } else {
      generatedTimeEl.textContent = 'Generated just now';
    }
  }

  if (datasetSummaryTextEl) {
    const total = data.total_records || 0;
    const channelsCount = 5;
    datasetSummaryTextEl.innerHTML = `Synthesized from <strong class="text-on-surface font-semibold">${total} qualitative records</strong> across evidence channels`;
  }

  if (datasetBadgeEl) {
    if (data.dataset === 'preloaded') {
      datasetBadgeEl.textContent = 'Preloaded benchmark';
      datasetBadgeEl.className = 'px-2.5 py-1 rounded-full bg-surface-container text-on-surface-variant text-xs font-semibold';
    } else {
      datasetBadgeEl.textContent = `Upload Job: ${data.dataset.substring(0, 8)}...`;
      datasetBadgeEl.className = 'px-2.5 py-1 rounded-full bg-primary-fixed/60 text-on-primary-fixed text-xs font-semibold';
    }
  }
}

function renderCards(cards) {
  const container = document.getElementById('cardsContainer');
  if (!container) return;

  if (!cards || cards.length === 0) {
    container.innerHTML = `
      <div class="p-8 rounded-xl bg-surface-container-lowest border border-outline-variant/20 text-center">
        <p class="text-sm text-on-surface-variant font-medium">No insight cards available for this dataset.</p>
      </div>
    `;
    return;
  }

  const html = cards.map(card => {
    const badge = getStrengthBadge(card.strength, card.supporting_count, card.strength_label);
    const explanationFormatted = escapeHtml(card.explanation).replace(/\n/g, '<br/>');

    // Evidence chips
    const chipsHtml = (card.supporting_evidence_ids || []).map(id => `
      <button 
        type="button" 
        class="evidence-chip px-2.5 py-1 rounded-lg bg-surface-container-low hover:bg-surface-container-high transition-colors font-mono text-xs text-primary font-semibold border border-outline-variant/30 cursor-pointer shadow-xs active:scale-[0.98]"
        data-id="${escapeHtml(id)}"
        title="View evidence record ${escapeHtml(id)}"
      >
        ${escapeHtml(id)}
      </button>
    `).join('');

    return `
      <article class="flex flex-col gap-4 p-6 rounded-xl bg-surface-container-lowest shadow-sm border border-outline-variant/20 hover:shadow-md transition-all">
        <!-- Top row: Strength Tag -->
        <div class="flex flex-wrap items-center justify-between gap-2">
          ${badge}
        </div>

        <!-- Headline & Explanation -->
        <div class="flex flex-col gap-2">
          <h2 class="text-xl font-bold text-on-surface tracking-tight leading-snug">
            ${escapeHtml(card.headline)}
          </h2>
          <p class="text-sm text-on-surface-variant leading-relaxed">
            ${explanationFormatted}
          </p>
        </div>

        <!-- Evidence Chips -->
        <div class="flex flex-col gap-1.5 pt-1">
          <span class="text-[11px] text-outline uppercase tracking-wider font-semibold">Evidence Logs</span>
          <div class="flex flex-wrap gap-1.5">
            ${chipsHtml || '<span class="text-xs text-outline italic">No supporting items cited</span>'}
          </div>
        </div>

        <!-- Proposed PM Action -->
        <div class="flex items-start gap-3 p-4 rounded-lg bg-primary-fixed/20 text-on-surface mt-1">
          <span class="material-symbols-outlined text-primary text-[20px] mt-0.5 shrink-0">lightbulb</span>
          <div class="flex flex-col">
            <span class="text-[11px] text-primary uppercase font-bold tracking-wider">Proposed PM Action Cue</span>
            <p class="text-sm text-on-surface font-medium mt-0.5 leading-normal">
              ${escapeHtml(card.proposed_pm_action)}
            </p>
          </div>
        </div>
      </article>
    `;
  }).join('');

  container.innerHTML = html;

  // Bind click listeners on evidence chips
  container.querySelectorAll('.evidence-chip').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const id = e.currentTarget.dataset.id;
      if (id) openEvidenceModal(id);
    });
  });
}

function renderNextQuestions(questions) {
  const container = document.getElementById('questionsContainer');
  const section = document.getElementById('nextQuestionsSection');
  if (!container || !section) return;

  if (!questions || questions.length === 0) {
    section.classList.add('hidden');
    return;
  }

  section.classList.remove('hidden');

  const html = questions.map((q, idx) => `
    <div class="p-4 rounded-xl bg-surface-container-lowest border border-outline-variant/20 transition-all text-left shadow-xs flex flex-col justify-between gap-3">
      <div class="flex items-start justify-between gap-1">
        <span class="text-xs text-primary font-bold uppercase tracking-wider">Question ${idx + 1}</span>
        <span class="material-symbols-outlined text-[16px] text-outline">help</span>
      </div>
      <p class="text-sm font-semibold text-on-surface leading-snug">
        &ldquo;${escapeHtml(q)}&rdquo;
      </p>
    </div>
  `).join('');

  container.innerHTML = html;
}

function renderSegmentView(segmentView) {
  const container = document.getElementById('segmentViewContainer');
  if (!container) return;

  if (!segmentView || segmentView.length === 0) {
    container.innerHTML = `
      <p class="text-xs text-on-surface-variant italic">No segment data available.</p>
    `;
    return;
  }

  const dotColors = {
    'Fixed salary': 'bg-primary',
    'Variable income (freelance/business)': 'bg-primary-container',
    'Student or dependent': 'bg-secondary',
    'Unclear': 'bg-outline',
  };

  const barColors = {
    'Fixed salary': 'bg-primary',
    'Variable income (freelance/business)': 'bg-primary-container',
    'Student or dependent': 'bg-secondary',
    'Unclear': 'bg-outline',
  };

  const html = segmentView.map(item => {
    const dot = dotColors[item.income_stability] || 'bg-outline';
    const bar = barColors[item.income_stability] || 'bg-primary';
    const pct = item.percentage !== undefined ? item.percentage : 0;
    const n = item.n !== undefined ? item.n : 0;

    return `
      <div class="flex flex-col gap-1.5 p-3 rounded-lg bg-surface-container-low border border-outline-variant/20">
        <div class="flex items-center justify-between text-xs font-semibold text-on-surface">
          <span class="flex items-center gap-2 truncate">
            <span class="w-2.5 h-2.5 rounded-full ${dot} shrink-0"></span>
            <span class="truncate" title="${escapeHtml(item.income_stability)}">${escapeHtml(item.income_stability)}</span>
          </span>
          <span class="font-mono font-bold shrink-0 ml-2">${pct}% <span class="text-[11px] text-outline font-normal">(n=${n})</span></span>
        </div>
        <div class="w-full bg-surface-container-highest h-2 rounded-full overflow-hidden">
          <div class="${bar} h-2 rounded-full transition-all duration-500 ease-out" style="width: ${Math.min(pct, 100)}%"></div>
        </div>
      </div>
    `;
  }).join('');

  container.innerHTML = html;
}

function renderAiUnavailableState(message) {
  const container = document.getElementById('cardsContainer');
  const section = document.getElementById('nextQuestionsSection');
  if (container) {
    container.innerHTML = `
      <div class="p-6 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 flex items-start gap-4 shadow-sm">
        <span class="material-symbols-outlined text-amber-700 text-[28px] shrink-0 mt-0.5">info</span>
        <div>
          <h3 class="text-base font-bold text-amber-900">AI Summary Unavailable</h3>
          <p class="text-sm text-amber-800 mt-1 leading-relaxed">
            ${escapeHtml(message || 'AI qualitative synthesis is currently offline or running in mock mode.')} 
            The quantitative segment view and computed statistics in the sidebar remain fully computed from the underlying dataset.
          </p>
        </div>
      </div>
    `;
  }
  if (section) {
    section.classList.add('hidden');
  }
}

async function openEvidenceModal(itemId) {
  const modal = document.getElementById('evidenceModal');
  const modalContent = document.getElementById('modalContent');
  const modalItemId = document.getElementById('modalItemId');

  if (!modal || !modalContent) return;

  if (modalItemId) modalItemId.textContent = itemId;
  modalContent.innerHTML = `
    <div class="flex items-center justify-center py-8 text-on-surface-variant">
      <span class="material-symbols-outlined animate-spin text-primary text-[28px]">sync</span>
      <span class="ml-2 text-sm font-medium">Loading record details...</span>
    </div>
  `;

  modal.showModal();

  try {
    const record = await api.getEvidenceById(itemId, currentDataset);
    renderModalRecord(record);
  } catch (err) {
    modalContent.innerHTML = `
      <div class="p-4 rounded-lg bg-error-container/40 border border-error/20 text-on-surface">
        <p class="text-sm font-semibold text-on-error-container">Could not load record ${escapeHtml(itemId)}</p>
        <p class="text-xs text-on-surface-variant mt-1">${parseApiError(err)}</p>
      </div>
    `;
  }
}

function renderModalRecord(rec) {
  const modalContent = document.getElementById('modalContent');
  if (!modalContent) return;

  const dateStr = rec.date ? escapeHtml(rec.date) : 'N/A';
  const ratingStr = rec.rating !== null && rec.rating !== undefined ? `${rec.rating} ★` : 'N/A';

  modalContent.innerHTML = `
    <div class="flex flex-col gap-4">
      <!-- Metadata Row -->
      <div class="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-outline-variant/20 text-xs">
        <div class="flex items-center gap-2">
          <span class="px-2.5 py-0.5 rounded-full bg-primary-fixed text-on-primary-fixed font-mono font-bold">${escapeHtml(rec.id)}</span>
          <span class="px-2 py-0.5 rounded-full bg-surface-container text-on-surface-variant uppercase font-medium text-[11px]">${escapeHtml(rec.source)}</span>
        </div>
        <div class="flex items-center gap-3 text-outline">
          <span>Date: <strong class="text-on-surface">${dateStr}</strong></span>
          <span>•</span>
          <span>Rating: <strong class="text-on-surface">${ratingStr}</strong></span>
        </div>
      </div>

      <!-- Verbatim Quote -->
      <div class="p-4 rounded-xl bg-surface-container-low border border-outline-variant/20">
        <span class="text-[11px] text-outline uppercase tracking-wider font-semibold block mb-1">Verbatim Feedback</span>
        <blockquote class="text-sm text-on-surface italic leading-relaxed">
          &ldquo;${escapeHtml(rec.text)}&rdquo;
        </blockquote>
      </div>

      <!-- Tagged Taxonomies Grid -->
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs">
        <div class="p-2.5 rounded-lg bg-surface-container-low border border-outline-variant/15">
          <span class="text-[10px] text-outline uppercase font-semibold block">Main Driver</span>
          <span class="font-semibold text-on-surface mt-0.5 block truncate" title="${escapeHtml(rec.main_driver)}">${escapeHtml(rec.main_driver)}</span>
        </div>
        <div class="p-2.5 rounded-lg bg-surface-container-low border border-outline-variant/15">
          <span class="text-[10px] text-outline uppercase font-semibold block">Outcome</span>
          <span class="font-semibold text-on-surface mt-0.5 block truncate" title="${escapeHtml(rec.outcome)}">${escapeHtml(rec.outcome)}</span>
        </div>
        <div class="p-2.5 rounded-lg bg-surface-container-low border border-outline-variant/15">
          <span class="text-[10px] text-outline uppercase font-semibold block">Stage</span>
          <span class="font-semibold text-on-surface mt-0.5 block truncate" title="${escapeHtml(rec.stage)}">${escapeHtml(rec.stage)}</span>
        </div>
        <div class="p-2.5 rounded-lg bg-surface-container-low border border-outline-variant/15">
          <span class="text-[10px] text-outline uppercase font-semibold block">Income Stability</span>
          <span class="font-semibold text-on-surface mt-0.5 block truncate" title="${escapeHtml(rec.income_stability)}">${escapeHtml(rec.income_stability)}</span>
        </div>
        <div class="p-2.5 rounded-lg bg-surface-container-low border border-outline-variant/15">
          <span class="text-[10px] text-outline uppercase font-semibold block">Age Band</span>
          <span class="font-semibold text-on-surface mt-0.5 block truncate" title="${escapeHtml(rec.age_band)}">${escapeHtml(rec.age_band)}</span>
        </div>
        <div class="p-2.5 rounded-lg bg-surface-container-low border border-outline-variant/15">
          <span class="text-[10px] text-outline uppercase font-semibold block">Unmet Need</span>
          <span class="font-semibold text-on-surface mt-0.5 block truncate" title="${escapeHtml(rec.unmet_need)}">${escapeHtml(rec.unmet_need)}</span>
        </div>
      </div>
    </div>
  `;
}

export async function loadInsights(forceRegenerate = false) {
  const btnRegen = document.getElementById('btnRegenerate');
  const regenIcon = document.getElementById('regenIcon');
  const errorContainer = document.getElementById('errorContainer');
  const errorMsg = document.getElementById('errorMessage');

  if (errorContainer) errorContainer.classList.add('hidden');

  // Loading state
  if (btnRegen) {
    btnRegen.disabled = true;
    btnRegen.classList.add('opacity-70');
  }
  if (regenIcon) {
    regenIcon.classList.add('animate-spin');
  }

  try {
    if (forceRegenerate) {
      insightsData = await api.regenerateInsights(currentDataset);
    } else {
      insightsData = await api.getInsights(currentDataset);
    }

    renderMetaRibbon(insightsData);
    renderSegmentView(insightsData.segment_view);
    renderDataWarnings(insightsData.data_warnings);

    if (insightsData.ai_summary_available) {
      renderCards(insightsData.cards);
      renderNextQuestions(insightsData.suggested_questions);
    } else {
      renderAiUnavailableState(insightsData.message);
    }
  } catch (err) {
    console.error('Failed to load insights:', err);
    if (errorContainer && errorMsg) {
      const errMsg = parseApiError(err);
      if (errMsg.toLowerCase().includes('expired') || errMsg.toLowerCase().includes('restarted')) {
        errorMsg.innerHTML = `${escapeHtml(errMsg)}<div class="mt-3"><a href="/upload" class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary text-on-primary rounded text-xs font-semibold hover:opacity-90"><span class="material-symbols-outlined text-[15px]">upload_file</span>Upload Dataset Again</a></div>`;
      } else {
        errorMsg.textContent = errMsg;
      }
      errorContainer.classList.remove('hidden');
    }
  } finally {
    if (btnRegen) {
      btnRegen.disabled = false;
      btnRegen.classList.remove('opacity-70');
    }
    if (regenIcon) {
      regenIcon.classList.remove('animate-spin');
    }
  }
}

export function initInsightsPage() {
  const urlParams = new URLSearchParams(window.location.search);
  const paramDataset = urlParams.get('dataset');
  if (paramDataset) {
    currentDataset = paramDataset;
  }

  // Regenerate Button
  const btnRegen = document.getElementById('btnRegenerate');
  if (btnRegen) {
    btnRegen.addEventListener('click', () => {
      loadInsights(true);
    });
  }

  // Modal Close & Dismiss Buttons
  const evidenceModal = document.getElementById('evidenceModal');
  const modalClose = document.getElementById('modalClose');
  const btnDismissModal = document.getElementById('btnDismissModal');

  if (evidenceModal) {
    if (modalClose) {
      modalClose.addEventListener('click', () => evidenceModal.close());
    }
    if (btnDismissModal) {
      btnDismissModal.addEventListener('click', () => evidenceModal.close());
    }
    evidenceModal.addEventListener('click', (e) => {
      const rect = evidenceModal.getBoundingClientRect();
      const inDialog = (
        rect.top <= e.clientY && e.clientY <= rect.top + rect.height &&
        rect.left <= e.clientX && e.clientX <= rect.left + rect.width
      );
      if (!inDialog) {
        evidenceModal.close();
      }
    });
  }

  // Initial load
  loadInsights(false);
}

document.addEventListener('DOMContentLoaded', () => {
  initInsightsPage();
});


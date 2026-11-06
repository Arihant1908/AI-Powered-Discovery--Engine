import { api } from './api.js';

const state = {
  filters: {
    source: '',
    income_stability: '',
    age_band: '',
    influence: ''
  },
  search: '',
  page: 1,
  pageSize: 10,
  selectedEvidenceId: null,
  isLoading: false
};

const OUTCOME_COLORS = {
  'Continuing': { stroke: '#006948', dot: 'bg-primary' },
  'Paused': { stroke: '#4edea3', dot: 'bg-tertiary-fixed-dim' },
  'Reduced': { stroke: '#565e74', dot: 'bg-secondary' },
  'Stopped': { stroke: '#ba1a1a', dot: 'bg-error' },
  'Unknown': { stroke: '#bccac0', dot: 'bg-outline-variant' }
};

const DRIVER_COLORS = [
  'bg-primary',
  'bg-primary-container',
  'bg-tertiary',
  'bg-error',
  'bg-error-container text-on-error-container',
  'bg-secondary',
  'bg-secondary-container',
  'bg-tertiary-fixed-dim',
  'bg-primary-fixed-dim',
  'bg-outline-variant',
  'bg-surface-container-highest'
];

// Elements
const els = {
  // Summary
  totalItems: document.getElementById('stat-total-items'),
  totalSources: document.getElementById('stat-sources'),
  sourcesSubtext: document.getElementById('stat-sources-subtext'),
  labelledItems: document.getElementById('stat-labelled-items'),
  deepInterviews: document.getElementById('stat-deep-interviews'),
  aiBadge: document.getElementById('ai-badge'),
  showingRecordsBadge: document.getElementById('showing-records-badge'),

  // Filters
  filterSource: document.getElementById('filter-source'),
  filterIncome: document.getElementById('filter-income'),
  filterAge: document.getElementById('filter-age'),
  filterInfluence: document.getElementById('filter-influence'),
  filterPills: document.getElementById('filter-pills-container'),
  btnResetAll: document.getElementById('btn-reset-all'),
  btnExportCsv: document.getElementById('btn-export-csv'),
  searchInput: document.getElementById('search-input'),

  // Visuals
  mainDriverContainer: document.getElementById('main-driver-container'),
  outcomeSvg: document.getElementById('outcome-donut-svg'),
  outcomeCenterPct: document.getElementById('outcome-center-pct'),
  outcomeCenterLabel: document.getElementById('outcome-center-label'),
  outcomeLegend: document.getElementById('outcome-legend'),

  // Unmet needs
  unmetNeedsContainer: document.getElementById('unmet-needs-container'),

  // Evidence
  evidenceTbody: document.getElementById('evidence-tbody'),
  evidenceInfo: document.getElementById('evidence-info'),
  paginationContainer: document.getElementById('pagination-container'),
  loadingOverlay: document.getElementById('loading-overlay'),
  errorBanner: document.getElementById('error-banner'),
  errorMessage: document.getElementById('error-message'),

  // Side Panel
  panelContainer: document.getElementById('evidence-side-panel'),
  panelTitle: document.getElementById('panel-title'),
  panelSource: document.getElementById('panel-source'),
  panelQuote: document.getElementById('panel-quote'),
  panelStage: document.getElementById('panel-stage'),
  panelIncome: document.getElementById('panel-income'),
  panelAge: document.getElementById('panel-age'),
  panelInfluence: document.getElementById('panel-influence'),
  panelDriver: document.getElementById('panel-driver'),
  panelOutcome: document.getElementById('panel-outcome')
};

function formatNumber(num) {
  if (num === null || num === undefined) return '0';
  return Number(num).toLocaleString('en-US');
}

function showLoading(show) {
  state.isLoading = show;
  if (els.loadingOverlay) {
    els.loadingOverlay.classList.toggle('hidden', !show);
  }
}

function showError(msg) {
  if (els.errorBanner && els.errorMessage) {
    els.errorMessage.textContent = msg || 'An error occurred loading dashboard data.';
    els.errorBanner.classList.remove('hidden');
  }
}

function clearError() {
  if (els.errorBanner) {
    els.errorBanner.classList.add('hidden');
  }
}

// 1. Populate Dropdowns from Meta API
async function initMeta() {
  try {
    const meta = await api.getMeta();
    const allowed = meta.allowed_values || {};
    const sources = meta.sources || [];

    // Sources dropdown
    if (els.filterSource) {
      els.filterSource.innerHTML = '<option value="">Source: All</option>';
      sources.forEach(src => {
        const opt = document.createElement('option');
        opt.value = src;
        opt.textContent = src.charAt(0).toUpperCase() + src.slice(1);
        els.filterSource.appendChild(opt);
      });
    }

    // Income Stability
    if (els.filterIncome && allowed.income_stability) {
      els.filterIncome.innerHTML = '<option value="">Income stability: All</option>';
      allowed.income_stability.forEach(val => {
        const opt = document.createElement('option');
        opt.value = val;
        opt.textContent = val;
        els.filterIncome.appendChild(opt);
      });
    }

    // Age Band
    if (els.filterAge && allowed.age_band) {
      els.filterAge.innerHTML = '<option value="">Age band: All</option>';
      allowed.age_band.forEach(val => {
        const opt = document.createElement('option');
        opt.value = val;
        opt.textContent = val;
        els.filterAge.appendChild(opt);
      });
    }

    // Influence
    if (els.filterInfluence && allowed.influence) {
      els.filterInfluence.innerHTML = '<option value="">Influence: All</option>';
      allowed.influence.forEach(val => {
        const opt = document.createElement('option');
        opt.value = val;
        opt.textContent = val;
        els.filterInfluence.appendChild(opt);
      });
    }
  } catch (err) {
    console.error('Failed to load metadata:', err);
    showError('Unable to load filter options. Please refresh.');
  }
}

// 2. Render Summary
function renderSummary(summary) {
  if (els.totalItems) els.totalItems.textContent = formatNumber(summary.total_items_collected);
  if (els.totalSources) els.totalSources.textContent = formatNumber(summary.distinct_sources);
  if (els.labelledItems) els.labelledItems.textContent = formatNumber(summary.labelled_evidence_items);
  if (els.deepInterviews) els.deepInterviews.textContent = formatNumber(summary.deep_interviews);
  if (els.showingRecordsBadge) {
    els.showingRecordsBadge.textContent = `Showing ${formatNumber(summary.labelled_evidence_items)} records`;
  }
}

// 3. Render Filter Pills
function renderFilterPills() {
  if (!els.filterPills) return;
  els.filterPills.innerHTML = '';

  const activePills = [];
  if (state.filters.source) activePills.push({ key: 'source', label: `Source: ${state.filters.source}` });
  if (state.filters.income_stability) activePills.push({ key: 'income_stability', label: `Income: ${state.filters.income_stability}` });
  if (state.filters.age_band) activePills.push({ key: 'age_band', label: `Age: ${state.filters.age_band}` });
  if (state.filters.influence) activePills.push({ key: 'influence', label: `Influence: ${state.filters.influence}` });
  if (state.search) activePills.push({ key: 'search', label: `Search: "${state.search}"` });

  if (activePills.length === 0) {
    els.filterPills.classList.add('hidden');
    return;
  }

  els.filterPills.classList.remove('hidden');
  activePills.forEach(pill => {
    const span = document.createElement('span');
    span.className = 'inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-surface-container text-on-surface-variant text-xs font-medium';
    span.innerHTML = `
      ${escapeHtml(pill.label)}
      <span class="material-symbols-outlined text-[13px] cursor-pointer hover:text-on-surface" data-key="${pill.key}">close</span>
    `;
    span.querySelector('[data-key]').addEventListener('click', () => {
      if (pill.key === 'search') {
        state.search = '';
        if (els.searchInput) els.searchInput.value = '';
      } else {
        state.filters[pill.key] = '';
        syncDropdowns();
      }
      state.page = 1;
      loadDashboard();
    });
    els.filterPills.appendChild(span);
  });
}

function syncDropdowns() {
  if (els.filterSource) els.filterSource.value = state.filters.source;
  if (els.filterIncome) els.filterIncome.value = state.filters.income_stability;
  if (els.filterAge) els.filterAge.value = state.filters.age_band;
  if (els.filterInfluence) els.filterInfluence.value = state.filters.influence;
}

// 4. Render Main Driver Bars
function renderMainDrivers(drivers = []) {
  if (!els.mainDriverContainer) return;
  els.mainDriverContainer.innerHTML = '';

  if (drivers.length === 0) {
    els.mainDriverContainer.innerHTML = '<p class="text-xs text-on-surface-variant py-4">No driver data for current filter.</p>';
    return;
  }

  drivers.forEach((d, idx) => {
    const colorClass = DRIVER_COLORS[idx % DRIVER_COLORS.length];
    const pct = d.percentage || 0;
    const cnt = d.count || 0;

    const row = document.createElement('div');
    row.className = 'flex flex-col gap-0.5';
    row.innerHTML = `
      <div class="flex items-center justify-between text-xs">
        <span class="text-on-surface font-medium truncate pr-2" title="${escapeHtml(d.label)}">${escapeHtml(d.label)}</span>
        <span class="text-on-surface-variant font-semibold whitespace-nowrap">${cnt} (${pct}%)</span>
      </div>
      <div class="w-full h-2 rounded-full bg-surface-container-low overflow-hidden">
        <div class="h-full ${colorClass} rounded-full transition-all duration-300" style="width: ${Math.min(100, Math.max(0, pct))}%"></div>
      </div>
    `;
    els.mainDriverContainer.appendChild(row);
  });
}

// 5. Render Outcome Donut Chart
function renderOutcomeDonut(outcomes = [], totalRecords = 0) {
  if (!els.outcomeSvg || !els.outcomeLegend) return;

  const C = 238.76; // Circumference for r=38
  let currentOffset = 0;
  let topOutcome = { label: 'None', percentage: 0 };

  // Clear previous segment circles (keep background track)
  const circles = els.outcomeSvg.querySelectorAll('.donut-segment');
  circles.forEach(c => c.remove());
  els.outcomeLegend.innerHTML = '';

  outcomes.forEach(item => {
    const pct = item.percentage || 0;
    const cnt = item.count || 0;
    const style = OUTCOME_COLORS[item.label] || { stroke: '#6d7a72', dot: 'bg-outline' };

    if (pct > topOutcome.percentage) {
      topOutcome = item;
    }

    if (pct > 0) {
      const segLength = (pct / 100) * C;
      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('class', 'donut-segment transition-all duration-300');
      circle.setAttribute('cx', '50');
      circle.setAttribute('cy', '50');
      circle.setAttribute('r', '38');
      circle.setAttribute('fill', 'transparent');
      circle.setAttribute('stroke', style.stroke);
      circle.setAttribute('stroke-width', '14');
      circle.setAttribute('stroke-dasharray', `${segLength.toFixed(2)} ${C.toFixed(2)}`);
      circle.setAttribute('stroke-dashoffset', (-currentOffset).toFixed(2));
      els.outcomeSvg.appendChild(circle);
      currentOffset += segLength;
    }

    // Legend item
    const legendRow = document.createElement('div');
    legendRow.className = 'flex items-center justify-between text-xs';
    legendRow.innerHTML = `
      <div class="flex items-center gap-2">
        <span class="w-3 h-3 rounded-full ${style.dot}"></span>
        <span class="text-on-surface font-medium">${escapeHtml(item.label)}</span>
      </div>
      <span class="text-on-surface-variant font-semibold">${cnt} (${pct}%)</span>
    `;
    els.outcomeLegend.appendChild(legendRow);
  });

  if (els.outcomeCenterPct) {
    els.outcomeCenterPct.textContent = totalRecords > 0 ? `${topOutcome.percentage}%` : '0%';
  }
  if (els.outcomeCenterLabel) {
    els.outcomeCenterLabel.textContent = totalRecords > 0 ? topOutcome.label : 'No data';
  }
}

// 6. Render Unmet Needs
function renderUnmetNeeds(themes = []) {
  if (!els.unmetNeedsContainer) return;
  els.unmetNeedsContainer.innerHTML = '';

  if (themes.length === 0) {
    els.unmetNeedsContainer.innerHTML = '<div class="col-span-full py-6 text-center text-xs text-on-surface-variant">No unmet need themes for this cohort.</div>';
    return;
  }

  themes.forEach((item, index) => {
    const card = document.createElement('div');
    card.className = 'p-4 rounded-xl bg-surface-container-low flex flex-col justify-between hover:bg-surface-container transition-colors';
    card.innerHTML = `
      <div>
        <span class="w-5 h-5 rounded-full ${index < 2 ? 'bg-primary text-on-primary' : 'bg-surface-container-highest text-on-surface'} inline-flex items-center justify-center text-xs font-bold mb-2">${index + 1}</span>
        <h3 class="text-sm font-semibold text-on-surface mb-1 leading-snug">${escapeHtml(item.theme)}</h3>
      </div>
      <div class="pt-3 text-xs font-semibold text-primary">${formatNumber(item.count)} mention${item.count === 1 ? '' : 's'}</div>
    `;
    els.unmetNeedsContainer.appendChild(card);
  });
}

// 7. Render Evidence Table & Pagination
function renderEvidenceTable(evidenceData) {
  if (!els.evidenceTbody) return;
  els.evidenceTbody.innerHTML = '';

  const items = evidenceData.items || [];
  const total = evidenceData.total || 0;
  const page = evidenceData.page || 1;
  const pageSize = evidenceData.page_size || 10;
  const totalPages = evidenceData.total_pages || 0;

  if (items.length === 0) {
    els.evidenceTbody.innerHTML = `
      <tr>
        <td colspan="7" class="py-8 text-center text-xs text-on-surface-variant">
          No matching evidence found. Try clearing or relaxing filters.
        </td>
      </tr>
    `;
    if (els.evidenceInfo) els.evidenceInfo.textContent = 'Showing 0 records';
    if (els.paginationContainer) els.paginationContainer.innerHTML = '';
    return;
  }

  const startRecord = (page - 1) * pageSize + 1;
  const endRecord = Math.min(page * pageSize, total);
  if (els.evidenceInfo) {
    els.evidenceInfo.textContent = `Showing ${startRecord}–${endRecord} of ${formatNumber(total)} records`;
  }

  // Auto-select first item if current selection not in items
  const foundCurrent = items.some(it => it.id === state.selectedEvidenceId);
  if (!foundCurrent && items.length > 0) {
    state.selectedEvidenceId = items[0].id;
    renderSidePanel(items[0]);
  }

  items.forEach(item => {
    const isSelected = item.id === state.selectedEvidenceId;
    const tr = document.createElement('tr');
    tr.className = `cursor-pointer transition-colors ${isSelected ? 'bg-primary-fixed/20 hover:bg-primary-fixed/30 font-medium' : 'hover:bg-surface-container-low'}`;
    tr.dataset.id = item.id;

    // Badges
    const outcomeStyle = getOutcomeBadgeClass(item.outcome);
    const textPreview = (item.text || '').length > 60 ? (item.text || '').substring(0, 57) + '...' : item.text;

    tr.innerHTML = `
      <td class="py-3 px-3 font-mono font-semibold text-primary whitespace-nowrap">${escapeHtml(item.id)}</td>
      <td class="py-3 px-3"><span class="px-2 py-0.5 rounded bg-surface-container text-on-surface-variant capitalize">${escapeHtml(item.source)}</span></td>
      <td class="py-3 px-3 text-on-surface-variant whitespace-nowrap">${escapeHtml(item.stage || 'Unclear')}</td>
      <td class="py-3 px-3"><span class="px-2 py-0.5 rounded-full bg-surface-container-high text-on-surface font-medium whitespace-nowrap">${escapeHtml(item.main_driver || 'Other')}</span></td>
      <td class="py-3 px-3"><span class="px-2 py-0.5 rounded-full ${outcomeStyle} font-medium whitespace-nowrap">${escapeHtml(item.outcome || 'Unknown')}</span></td>
      <td class="py-3 px-3 font-medium text-on-surface truncate max-w-[140px]" title="${escapeHtml(item.unmet_need || 'none')}">${escapeHtml(item.unmet_need || 'none')}</td>
      <td class="py-3 px-3 text-on-surface-variant truncate max-w-[180px]" title="${escapeHtml(item.text || '')}">"${escapeHtml(textPreview)}"</td>
    `;

    tr.addEventListener('click', () => {
      state.selectedEvidenceId = item.id;
      // Update row selection style
      els.evidenceTbody.querySelectorAll('tr').forEach(r => {
        r.classList.remove('bg-primary-fixed/20', 'hover:bg-primary-fixed/30');
        r.classList.add('hover:bg-surface-container-low');
      });
      tr.classList.remove('hover:bg-surface-container-low');
      tr.classList.add('bg-primary-fixed/20', 'hover:bg-primary-fixed/30');
      renderSidePanel(item);
    });

    els.evidenceTbody.appendChild(tr);
  });

  // Pagination controls
  renderPagination(page, totalPages);
}

function getOutcomeBadgeClass(outcome) {
  switch (outcome) {
    case 'Continuing': return 'bg-primary-fixed text-on-primary-fixed';
    case 'Paused': return 'bg-tertiary-fixed text-on-tertiary-fixed';
    case 'Reduced': return 'bg-secondary-container text-on-secondary-container';
    case 'Stopped': return 'bg-error-container text-on-error-container';
    default: return 'bg-surface-container text-outline';
  }
}

function renderPagination(currentPage, totalPages) {
  if (!els.paginationContainer) return;
  els.paginationContainer.innerHTML = '';

  if (totalPages <= 1) return;

  // Prev
  const prevBtn = document.createElement('button');
  prevBtn.className = `px-2 py-0.5 rounded text-xs transition-colors ${currentPage > 1 ? 'hover:bg-surface-container text-on-surface cursor-pointer' : 'text-outline cursor-not-allowed opacity-50'}`;
  prevBtn.textContent = 'Prev';
  prevBtn.disabled = currentPage <= 1;
  prevBtn.addEventListener('click', () => {
    if (currentPage > 1) {
      state.page = currentPage - 1;
      loadEvidenceOnly();
    }
  });
  els.paginationContainer.appendChild(prevBtn);

  // Page numbers (max 5 around current)
  const maxButtons = 5;
  let startP = Math.max(1, currentPage - Math.floor(maxButtons / 2));
  let endP = Math.min(totalPages, startP + maxButtons - 1);
  if (endP - startP + 1 < maxButtons) {
    startP = Math.max(1, endP - maxButtons + 1);
  }

  for (let p = startP; p <= endP; p++) {
    const pBtn = document.createElement('button');
    const isActive = p === currentPage;
    pBtn.className = `px-2 py-0.5 rounded text-xs font-semibold ${isActive ? 'bg-primary text-on-primary' : 'hover:bg-surface-container text-on-surface'}`;
    pBtn.textContent = p;
    pBtn.addEventListener('click', () => {
      if (p !== currentPage) {
        state.page = p;
        loadEvidenceOnly();
      }
    });
    els.paginationContainer.appendChild(pBtn);
  }

  // Next
  const nextBtn = document.createElement('button');
  nextBtn.className = `px-2 py-0.5 rounded text-xs transition-colors ${currentPage < totalPages ? 'hover:bg-surface-container text-on-surface cursor-pointer' : 'text-outline cursor-not-allowed opacity-50'}`;
  nextBtn.textContent = 'Next';
  nextBtn.disabled = currentPage >= totalPages;
  nextBtn.addEventListener('click', () => {
    if (currentPage < totalPages) {
      state.page = currentPage + 1;
      loadEvidenceOnly();
    }
  });
  els.paginationContainer.appendChild(nextBtn);
}

// 8. Render Side Panel
function renderSidePanel(item) {
  if (!item) return;
  if (els.panelTitle) els.panelTitle.textContent = `Evidence: ${item.id}`;
  if (els.panelSource) els.panelSource.textContent = item.source ? item.source.toUpperCase() : 'VERIFIED';
  if (els.panelQuote) els.panelQuote.textContent = item.text ? `"${item.text}"` : 'No text content available.';
  if (els.panelStage) els.panelStage.textContent = item.stage || 'Unclear';
  if (els.panelIncome) els.panelIncome.textContent = item.income_stability || 'Unclear';
  if (els.panelAge) els.panelAge.textContent = item.age_band || 'Unclear';
  if (els.panelInfluence) els.panelInfluence.textContent = item.influence || 'Unclear';
  if (els.panelDriver) els.panelDriver.textContent = item.main_driver || 'Other';
  if (els.panelOutcome) els.panelOutcome.textContent = item.outcome || 'Unknown';
}

// 9. Fetch and load all Dashboard components
async function loadDashboard() {
  clearError();
  showLoading(true);

  try {
    const [summary, charts, unmetNeeds, evidence] = await Promise.all([
      api.getSummary(state.filters),
      api.getCharts(state.filters),
      api.getUnmetNeeds(state.filters),
      api.getEvidence({
        ...state.filters,
        search: state.search,
        page: state.page,
        page_size: state.pageSize
      })
    ]);

    renderSummary(summary);
    renderFilterPills();
    renderMainDrivers(charts.main_driver);
    renderOutcomeDonut(charts.outcome, charts.total_records);
    renderUnmetNeeds(unmetNeeds.themes);
    renderEvidenceTable(evidence);
  } catch (err) {
    console.error('Error loading dashboard:', err);
    showError(err?.error?.message || 'Failed to load dashboard data. Please check connectivity.');
  } finally {
    showLoading(false);
  }
}

// Pagination / Search reload
async function loadEvidenceOnly() {
  showLoading(true);
  try {
    const evidence = await api.getEvidence({
      ...state.filters,
      search: state.search,
      page: state.page,
      page_size: state.pageSize
    });
    renderEvidenceTable(evidence);
  } catch (err) {
    console.error('Error loading evidence:', err);
    showError('Failed to load evidence page.');
  } finally {
    showLoading(false);
  }
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// 10. Setup Event Handlers
function setupEventListeners() {
  // Filter Dropdowns
  const handleFilterChange = (key, el) => {
    state.filters[key] = el.value;
    state.page = 1;
    loadDashboard();
  };

  if (els.filterSource) {
    els.filterSource.addEventListener('change', () => handleFilterChange('source', els.filterSource));
  }
  if (els.filterIncome) {
    els.filterIncome.addEventListener('change', () => handleFilterChange('income_stability', els.filterIncome));
  }
  if (els.filterAge) {
    els.filterAge.addEventListener('change', () => handleFilterChange('age_band', els.filterAge));
  }
  if (els.filterInfluence) {
    els.filterInfluence.addEventListener('change', () => handleFilterChange('influence', els.filterInfluence));
  }

  // Reset All
  if (els.btnResetAll) {
    els.btnResetAll.addEventListener('click', () => {
      state.filters = { source: '', income_stability: '', age_band: '', influence: '' };
      state.search = '';
      state.page = 1;
      if (els.searchInput) els.searchInput.value = '';
      syncDropdowns();
      loadDashboard();
    });
  }

  // Search input debounced
  let searchTimeout = null;
  if (els.searchInput) {
    els.searchInput.addEventListener('input', (e) => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        state.search = e.target.value.trim();
        state.page = 1;
        loadEvidenceOnly();
      }, 250);
    });
  }

  // Export CSV
  if (els.btnExportCsv) {
    els.btnExportCsv.addEventListener('click', () => {
      const url = api.getExportUrl({
        ...state.filters,
        search: state.search
      });
      window.location.href = url;
    });
  }
}

// Initialization on DOMContentLoaded
window.addEventListener('DOMContentLoaded', async () => {
  setupEventListeners();
  await initMeta();
  await loadDashboard();
});


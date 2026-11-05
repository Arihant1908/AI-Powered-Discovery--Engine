// api.js - Dashboard API client

const API_BASE = '/api';

function buildQuery(params = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      if (Array.isArray(value)) {
        value.forEach(v => {
          if (v) query.append(key, v);
        });
      } else {
        query.append(key, value);
      }
    }
  }
  const str = query.toString();
  return str ? `?${str}` : '';
}

async function request(endpoint, options = {}) {
  try {
    const response = await fetch(`${API_BASE}${endpoint}`, options);
    if (!response.ok) {
      let errPayload;
      try {
        errPayload = await response.json();
      } catch (_) {
        errPayload = { error: { code: `HTTP_${response.status}`, message: response.statusText } };
      }
      throw errPayload;
    }
    return await response.json();
  } catch (err) {
    console.error(`API Error on ${endpoint}:`, err);
    throw err;
  }
}

export const api = {
  async getMeta() {
    return request('/meta');
  },

  async getSummary(filters = {}) {
    return request(`/dashboard/summary${buildQuery(filters)}`);
  },

  async getCharts(filters = {}) {
    return request(`/dashboard/charts${buildQuery(filters)}`);
  },

  async getUnmetNeeds(filters = {}) {
    return request(`/dashboard/unmet-needs${buildQuery(filters)}`);
  },

  async getEvidence(params = {}) {
    return request(`/dashboard/evidence${buildQuery(params)}`);
  },

  async getEvidenceById(id, dataset = null) {
    const query = dataset ? `?dataset=${encodeURIComponent(dataset)}` : '';
    return request(`/dashboard/evidence/${encodeURIComponent(id)}${query}`);
  },

  getExportUrl(filters = {}) {
    return `${API_BASE}/dashboard/export.csv${buildQuery(filters)}`;
  },

  async uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    return request('/upload', {
      method: 'POST',
      body: formData,
    });
  },

  async uploadSample() {
    return request('/upload/sample', {
      method: 'POST',
    });
  },

  async getJobStatus(jobId) {
    return request(`/upload/${encodeURIComponent(jobId)}/status`);
  },

  async getJobRows(jobId, page = 1, pageSize = 10) {
    return request(`/upload/${encodeURIComponent(jobId)}/rows?page=${page}&page_size=${pageSize}`);
  },

  async updateJobRow(jobId, rowId, updates) {
    return request(`/upload/${encodeURIComponent(jobId)}/rows/${encodeURIComponent(rowId)}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(updates),
    });
  },

  async getInsights(dataset = 'preloaded') {
    return request(`/insights?dataset=${encodeURIComponent(dataset)}`);
  },

  async regenerateInsights(dataset = 'preloaded') {
    return request(`/insights/regenerate?dataset=${encodeURIComponent(dataset)}`, {
      method: 'POST',
    });
  }
};


// Centralized fetch wrapper. Every panel calls through this module so error
// handling, base URL, and JSON parsing live in one place.

const BASE = '/api';

async function request(path, { method = 'GET', body, signal } = {}) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
    signal,
  };
  if (body !== undefined) opts.body = JSON.stringify(body);

  const res = await fetch(`${BASE}${path}`, opts);
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { raw: text };
    }
  }
  if (!res.ok) {
    const detail =
      (data && (data.detail || data.message)) ||
      `${res.status} ${res.statusText}`;
    const err = new Error(detail);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

export const api = {
  // agent
  startAgent: () => request('/agent/start', { method: 'POST' }),
  chat: (session_id, message) =>
    request('/agent/chat', { method: 'POST', body: { session_id, message } }),

  // status
  statusSummary: () => request('/status/summary'),
  statusContracts: (limit = 200) => request(`/status/contracts?limit=${limit}`),
  statusAsk: (question) =>
    request('/status/ask', { method: 'POST', body: { question } }),

  // analysis
  deliveries: () => request('/analysis/deliveries'),
  setupAnalysis: (payload) =>
    request('/analysis/setup', { method: 'POST', body: payload }),
  askAnalysis: (session_id, question) =>
    request('/analysis/ask', {
      method: 'POST',
      body: { session_id, question },
    }),

  // reports
  reconciliation: (session_id) =>
    request('/reports/reconciliation', {
      method: 'POST',
      body: { session_id },
    }),
  audit: () => request('/reports/audit'),

  // health
  health: () => request('/health'),
};

export default api;

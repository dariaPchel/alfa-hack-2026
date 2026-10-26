const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.message || `API request failed: ${response.status}`);
  return payload;
}

export async function getCompanies(query = '') {
  const suffix = query ? `?q=${encodeURIComponent(query)}` : '';
  const payload = await request(`/companies${suffix}`);
  return payload.companies || [];
}

export async function getCompanyNews(companyId) {
  const payload = await request(`/companies/${encodeURIComponent(companyId)}/news`);
  const windows = payload.windows || {};
  for (const name of ['24h', '7d', '90d']) {
    if (windows[name]?.events?.length) return { events: windows[name].events, window: name, updatedAt: windows[name].updated_at, refresh: payload.refresh || {} };
  }
  return { events: [], window: '90d', updatedAt: '', refresh: payload.refresh || {} };
}

export async function startAnalysis(companyId, eventId, question) {
  return request(`/companies/${encodeURIComponent(companyId)}/analyze`, { method: 'POST', body: JSON.stringify({ event_ids: [eventId], question }) });
}

export async function getAnalysis(analysisId) {
  const payload = await request(`/analyses/${encodeURIComponent(analysisId)}`);
  return payload.analysis;
}

export async function submitFeedback(analysisId, rating, comment = '') {
  return request(`/analyses/${encodeURIComponent(analysisId)}/feedback`, {
    method: 'POST',
    body: JSON.stringify({ rating, comment }),
  });
}

export async function requestNewsRefresh(companyId) {
  return request(`/companies/${encodeURIComponent(companyId)}/news/refresh`, { method: 'POST' });
}

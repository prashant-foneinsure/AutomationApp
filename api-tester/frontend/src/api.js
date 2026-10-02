const BASE = '/api/modules'

async function request(method, path, body) {
  const options = { method, headers: {} }
  if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(body)
  }
  const response = await fetch(`${BASE}${path}`, options)
  const text = await response.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = { detail: text }
  }
  if (!response.ok) {
    const detail = data && data.detail
    const message = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ')
        : `Request failed (${response.status})`
    const error = new Error(message)
    error.status = response.status
    throw error
  }
  return data
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body ?? {}),
  put: (path, body) => request('PUT', path, body ?? {}),
  del: (path) => request('DELETE', path),
}

// ---------- meta ----------
export const getHealth = () => fetch('/api/health').then((r) => r.json())

// ---------- api-testing ----------
const AT = '/api-testing'

export const groups = {
  list: () => request('GET', `${AT}/groups`),
  get: (id) => request('GET', `${AT}/groups/${id}`),
  create: (body) => request('POST', `${AT}/groups`, body),
  update: (id, body) => request('PUT', `${AT}/groups/${id}`, body),
  remove: (id) => request('DELETE', `${AT}/groups/${id}`),
}

export const tests = {
  list: (groupId) => request('GET', `${AT}/groups/${groupId}/tests`),
  create: (groupId, body) => request('POST', `${AT}/groups/${groupId}/tests`, body),
  update: (testId, body) => request('PUT', `${AT}/tests/${testId}`, body),
  remove: (testId) => request('DELETE', `${AT}/tests/${testId}`),
}

export const runs = {
  listForTest: (testId) => request('GET', `${AT}/tests/${testId}/runs`),
  get: (runId) => request('GET', `${AT}/runs/${runId}`),
  recent: (limit = 25) => request('GET', `${AT}/recent?limit=${limit}`),
  insights: (testId) => request('GET', `${AT}/tests/${testId}/insights`),
  feedback: (runId, caseId, body) =>
    request('POST', `${AT}/runs/${runId}/cases/${caseId}/feedback`, body),
}

export const execute = {
  test: (testId, body) => request('POST', `${AT}/tests/${testId}/run`, body),
  group: (groupId, body) => request('POST', `${AT}/groups/${groupId}/run`, body),
  adhoc: (body) => request('POST', `${AT}/run-adhoc`, body),
  proposeExtractors: (testId, body) =>
    request('POST', `${AT}/tests/${testId}/propose-extractors`, body),
}

export const variables = {
  list: (groupId) => request('GET', `${AT}/groups/${groupId}/variables`),
  update: (groupId, name, value) =>
    request('PUT', `${AT}/groups/${groupId}/variables/${encodeURIComponent(name)}`, { value }),
  remove: (groupId, name) =>
    request('DELETE', `${AT}/groups/${groupId}/variables/${encodeURIComponent(name)}`),
}

export const status = () => request('GET', `${AT}/status`)

const BASE = ''

export async function fetchMeta() {
  const res = await fetch(`${BASE}/api/meta`)
  if (!res.ok) throw new Error('Failed to load metadata')
  return res.json()
}

export async function fetchRecommendations(payload) {
  const res = await fetch(`${BASE}/api/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Recommendation request failed')
  }
  return res.json()
}

export async function fetchHistory(farmerId) {
  const res = await fetch(`${BASE}/api/history/${encodeURIComponent(farmerId)}`)
  if (!res.ok) throw new Error('Failed to load history')
  return res.json()
}

export async function logSeason(record) {
  const res = await fetch(`${BASE}/api/history`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(record),
  })
  if (!res.ok) throw new Error('Failed to log season')
  return res.json()
}

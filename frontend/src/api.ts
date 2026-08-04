import type { Check } from './types'

/** One provider, with its latest result and a short run of recent ones. */
export type ProviderGroup = {
  provider: string
  latest: Check
  recent: Check[] // oldest first — the order the strip is drawn in
}

export async function fetchHistory(limit = 200): Promise<Check[]> {
  const response = await fetch(`/api/history?limit=${limit}`)
  // fetch only throws if the request could not be made at all. A 500 still
  // counts as "success" to fetch, so we check the status ourselves.
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

/**
 * Turn one flat list of checks into one entry per provider.
 *
 * We ask the API for history once and split it up here, rather than making a
 * separate request per provider. Four providers x 30 blocks is 120 rows, well
 * inside the 200 we fetch.
 */
export function groupByProvider(
  checks: Check[],
  stripLength = 30,
): ProviderGroup[] {
  const byProvider = new Map<string, Check[]>()

  for (const check of checks) {
    const rows = byProvider.get(check.provider) ?? []
    rows.push(check)
    byProvider.set(check.provider, rows)
  }

  return [...byProvider.entries()]
    .map(([provider, rows]) => ({
      provider,
      // The API returns newest first, so row 0 is the current state.
      latest: rows[0],
      // The strip reads left to right as oldest to newest, like a timeline.
      recent: rows.slice(0, stripLength).reverse(),
    }))
    .sort((a, b) => a.provider.localeCompare(b.provider))
}

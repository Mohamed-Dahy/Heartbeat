import { useCallback, useEffect, useState } from 'react'
import { fetchHistory, groupByProvider, type ProviderGroup } from './api'
import { ProviderCard } from './ProviderCard'

// Checks happen every 60 seconds, so refreshing every 30 guarantees the page is
// never more than half a cycle out of date.
const REFRESH_MS = 30_000

export default function App() {
  const [groups, setGroups] = useState<ProviderGroup[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)

  const load = useCallback(async () => {
    try {
      const checks = await fetchHistory()
      setGroups(groupByProvider(checks))
      setUpdatedAt(new Date())
      // Clear a previous failure once we succeed again.
      setError(null)
    } catch (err) {
      // Keep whatever we last had on screen, but say clearly that it is stale.
      // A status page that silently shows old data is worse than one that
      // admits it is broken.
      setError(String(err))
    }
  }, [])

  useEffect(() => {
    load()
    const timer = setInterval(load, REFRESH_MS)
    // React runs this when the component goes away. Without it, every reload
    // during development would leave another timer running forever.
    return () => clearInterval(timer)
  }, [load])

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-3xl p-6 sm:p-10">
        <header>
          <h1 className="text-2xl font-semibold">Heartbeat</h1>
          <p className="mt-1 text-sm text-slate-400">
            Are the major LLM APIs answering, and how fast? Checked every 60
            seconds.
          </p>
        </header>

        {error && (
          <p className="mt-6 rounded border border-red-900 bg-red-950/60 p-4 text-sm text-red-300">
            Could not reach the API ({error}). Anything below is the last data we
            managed to load.
          </p>
        )}

        {!error && groups === null && (
          <p className="mt-6 text-slate-400">Loading…</p>
        )}

        {groups?.length === 0 && (
          <p className="mt-6 text-slate-400">
            No checks recorded yet. The first round runs a second after the
            server starts — wait a moment.
          </p>
        )}

        {groups && groups.length > 0 && (
          <main className="mt-6 grid gap-4">
            {groups.map((group) => (
              <ProviderCard key={group.provider} group={group} />
            ))}
          </main>
        )}

        <footer className="mt-8 flex justify-between text-xs text-slate-500">
          <span>
            {updatedAt
              ? `Updated ${updatedAt.toLocaleTimeString()}`
              : 'Not updated yet'}
          </span>
          <span>Times shown in your local timezone</span>
        </footer>
      </div>
    </div>
  )
}

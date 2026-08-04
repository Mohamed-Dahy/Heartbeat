import type { ProviderGroup } from './api'
import type { Check } from './types'
import { HistoryStrip } from './HistoryStrip'

const STATUS_TEXT: Record<Check['status'], string> = {
  up: 'text-emerald-400',
  slow: 'text-amber-400',
  down: 'text-red-400',
}

const STATUS_DOT: Record<Check['status'], string> = {
  up: 'bg-emerald-500',
  slow: 'bg-amber-500',
  down: 'bg-red-500',
}

/** How many of the recent checks were reachable. */
function uptimePercent(checks: Check[]): number {
  if (checks.length === 0) return 0
  const reachable = checks.filter((check) => check.status !== 'down').length
  return Math.round((reachable / checks.length) * 100)
}

export function ProviderCard({ group }: { group: ProviderGroup }) {
  const { provider, latest, recent } = group

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900 p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold capitalize">{provider}</h2>

        <div className="flex items-center gap-2">
          <span
            className={`inline-block h-2.5 w-2.5 rounded-full ${
              STATUS_DOT[latest.status]
            }`}
          />
          <span className={`font-medium ${STATUS_TEXT[latest.status]}`}>
            {latest.status}
          </span>
          <span className="text-sm text-slate-400">
            {Math.round(latest.response_time_ms)} ms
          </span>
        </div>
      </div>

      <div className="mt-4">
        <HistoryStrip checks={recent} />
      </div>

      <div className="mt-2 flex justify-between text-xs text-slate-500">
        <span>{recent.length} checks</span>
        <span>{uptimePercent(recent)}% reachable</span>
      </div>

      {latest.error && (
        <p className="mt-3 text-xs text-red-400">Last error: {latest.error}</p>
      )}
    </section>
  )
}

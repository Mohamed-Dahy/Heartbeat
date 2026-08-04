import type { Check } from './types'

const STATUS_COLOUR: Record<Check['status'], string> = {
  up: 'bg-emerald-500',
  slow: 'bg-amber-500',
  down: 'bg-red-500',
}

/**
 * The classic status-page bar: one small block per check, oldest on the left.
 *
 * No charting library. An outage is a run of red blocks, which you can see from
 * across the room — that is all a chart would have told us anyway.
 */
export function HistoryStrip({ checks }: { checks: Check[] }) {
  if (checks.length === 0) {
    return <p className="text-xs text-slate-500">No history yet.</p>
  }

  return (
    <div className="flex gap-[3px]" role="img" aria-label="Recent check history">
      {checks.map((check) => (
        <div
          key={check.id}
          // title gives a free tooltip on hover — no library needed.
          title={`${new Date(check.checked_at).toLocaleTimeString()} — ${
            check.status
          }, ${Math.round(check.response_time_ms)} ms`}
          className={`h-8 min-w-[3px] flex-1 rounded-sm ${
            STATUS_COLOUR[check.status]
          }`}
        />
      ))}
    </div>
  )
}

/** One row from the checks table, exactly as the API returns it. */
export type Check = {
  id: number
  provider: string
  url: string
  status: 'up' | 'slow' | 'down'
  response_time_ms: number
  status_code: number | null
  error: string | null
  checked_at: string
}

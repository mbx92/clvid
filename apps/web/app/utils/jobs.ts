import type { Job } from '~/types/api'

function utcMilliseconds(value?: string): number | null {
  if (!value) return null
  const time = Date.parse(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`)
  return Number.isFinite(time) ? time : null
}

/** Elapsed work time from server timestamps, never an estimated completion time. */
export function jobElapsedMs(job: Pick<Job, 'status' | 'started_at' | 'finished_at'>, now: number): number | null {
  if (job.status === 'queued') return null
  const start = utcMilliseconds(job.started_at)
  if (start === null) return null
  const end = ['running', 'cancel_requested'].includes(job.status) ? now : utcMilliseconds(job.finished_at)
  return end === null ? null : Math.max(0, end - start)
}

export function elapsedLabel(milliseconds: number): string {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000))
  if (seconds < 60) return `${seconds} dtk`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} mnt ${seconds % 60} dtk`
  return `${Math.floor(seconds / 3600)} jam ${Math.floor(seconds / 60) % 60} mnt`
}

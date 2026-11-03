export function timecode(ms = 0, precise = false): string {
  const value = Math.max(0, Math.round(Number(ms) || 0))
  const hours = Math.floor(value / 3600000)
  const minutes = Math.floor(value / 60000) % 60
  const seconds = Math.floor(value / 1000) % 60
  const result = `${hours ? `${hours.toString().padStart(2, '0')}:` : ''}${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
  return precise ? `${result}.${(value % 1000).toString().padStart(3, '0')}` : result
}
export function parseTimecode(input: string): number | null {
  if (!/^\d+(?::[0-5]?\d){0,2}(?:[.,]\d{1,3})?$/.test(input.trim())) return null
  const pieces = input.trim().replace(',', '.').split(':').map(Number)
  return Math.round(pieces.reduce((total, value) => total * 60 + value, 0) * 1000)
}
export function fileSize(bytes = 0): string {
  if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(1)} GiB`
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MiB`
  return `${Math.round(bytes / 1024)} KiB`
}
export function dateTime(value?: string): string {
  return value ? new Intl.DateTimeFormat('id-ID', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`)) : '—'
}
export const statusLabels: Record<string, string> = {
  importing: 'Mengimpor video',
  draft: 'Belum ada video', uploading: 'Mengunggah', uploaded: 'Menunggu validasi', validating: 'Memvalidasi', ready: 'Siap ditinjau', processing: 'Sedang diproses', transcribing: 'Memproses transkrip', analyzing: 'Memilih kandidat', failed: 'Gagal', error: 'Gagal', queued: 'Dalam antrean', running: 'Sedang berjalan', succeeded: 'Selesai', cancelled: 'Dibatalkan', cancel_requested: 'Menunggu pembatalan', deleting: 'Sedang dihapus', deleted: 'Dihapus', no_speech: 'Tidak ditemukan ucapan', validated: 'Video siap', completed: 'Selesai', empty: 'Belum ada video', active: 'Aktif',
}
export const stageLabels: Record<string, string> = { import_url: 'Mengunduh video dari URL', validate: 'Memvalidasi video', prepare_preview: 'Menyiapkan preview', transcribe: 'Memproses transkrip', subtitle_generate: 'Membuat subtitle dari audio klip', analyze: 'Memilih kandidat', analyze_frames: 'Memeriksa frame gameplay', track_preview: 'Menyiapkan analisis preview', track_faces: 'Menganalisis gerak wajah', render: 'Merender video', render_remotion: 'Menganimasikan subtitle dengan Remotion', finalize_render: 'Menyelesaikan video dan audio', delete_assets: 'Menghapus aset' }
export function isActive(status: string): boolean { return ['queued', 'running', 'cancel_requested'].includes(status) }

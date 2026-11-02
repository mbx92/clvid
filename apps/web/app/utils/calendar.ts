export const timezones = [
  { value: 'Asia/Makassar', label: 'WITA (UTC+8)' },
  { value: 'Asia/Jakarta', label: 'WIB (UTC+7)' },
  { value: 'Asia/Jayapura', label: 'WIT (UTC+9)' },
  { value: 'UTC', label: 'UTC' },
]
const offsets: Record<string, number> = { 'Asia/Makassar': 8, 'Asia/Jakarta': 7, 'Asia/Jayapura': 9, UTC: 0 }
export function localInput(value: string | Date, timezone: string) {
  return new Date(new Date(value).getTime() + offsets[timezone]! * 3600000).toISOString().slice(0, 16)
}
export function utcInput(value: string, timezone: string) {
  return new Date(Date.parse(value + ':00Z') - offsets[timezone]! * 3600000).toISOString()
}
export function monthCells(month: string) {
  const first = new Date(month + '-01T00:00:00Z')
  const begin = first.getTime() - (first.getUTCDay() + 6) % 7 * 86400000
  return Array.from({ length: 42 }, (_, i) => new Date(begin + i * 86400000).toISOString().slice(0, 10))
}
export function moveMonth(month: string, delta: number) {
  const date = new Date(month + '-01T00:00:00Z')
  date.setUTCMonth(date.getUTCMonth() + delta)
  return date.toISOString().slice(0, 7)
}
export const platformLabels: Record<string, string> = { youtube: 'YouTube / Shorts', instagram: 'Instagram Reels', tiktok: 'TikTok' }
export const publicationLabels: Record<string, string> = { draft: 'Draft', scheduled: 'Terjadwal', uploading: 'Mengunggah', processing: 'Diproses platform', published: 'Selesai', failed: 'Gagal', uncertain: 'Perlu diperiksa', cancelled: 'Dibatalkan' }

type PublicationAccount = { id: string; platform: string; connected?: boolean }
type PublicationPlatform = { id: string; configured: boolean; publishing_ready: boolean }
export function publicationReadiness(platform: string, accountId: string, accounts: PublicationAccount[], platforms: PublicationPlatform[]) {
  const config = platforms.find(item => item.id === platform)
  const available = accounts.filter(item => item.platform === platform && item.connected !== false)
  const label = platformLabels[platform] || platform
  if (!config?.configured) return { ready: false, manageConnection: true, message: `Konfigurasi ${label} belum lengkap.` }
  if (!available.length) return { ready: false, manageConnection: true, message: `Belum ada akun ${label} yang terhubung.` }
  if (!available.some(item => item.id === accountId)) return { ready: false, manageConnection: false, message: `Akun ${label} sudah terhubung. Pilih Akun tujuan pada bagian Video & jadwal.` }
  if (!config.publishing_ready) return { ready: false, manageConnection: true, message: platform === 'instagram' ? 'Publikasi Instagram memerlukan URL HTTPS publik untuk video.' : platform === 'tiktok' ? 'Akses publikasi otomatis TikTok belum diaktifkan.' : `Konfigurasi publikasi ${label} belum siap.` }
  return { ready: true, manageConnection: false, message: '' }
}

export function singlePublicationAccount(platform: string, accounts: PublicationAccount[]) {
  const available = accounts.filter(item => item.platform === platform && item.connected !== false)
  return available.length === 1 ? available[0]!.id : ''
}

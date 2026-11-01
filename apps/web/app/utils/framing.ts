import type { Crop, ExportFramingMetadata, TrackingMode } from '~/types/api'
import { defaultGaming } from './gaming.ts'

export const trackingOptions: { value: TrackingMode; label: string }[] = [
  { value: 'static', label: 'Manual (tetap)' },
  { value: 'face', label: 'Ikuti wajah' },
  { value: 'speaker', label: 'Ikuti pembicara (perkiraan)' },
]

export function trackingLabel(mode: TrackingMode): string {
  return trackingOptions.find(option => option.value === mode)?.label || 'Manual (tetap)'
}

/** Legacy revisions remain unchanged; the missing setting means a fixed crop. */
export function cropTracking(crop?: Crop): TrackingMode {
  return crop?.mode === 'fill' ? crop.tracking || 'static' : 'static'
}

export function cropWithMode(crop: Crop, mode: Crop['mode']): Crop {
  if (mode === 'gaming') return { ...crop, mode, tracking: 'static', gaming: crop.gaming || defaultGaming() }
  const { gaming: _gaming, ...single } = crop
  return mode === 'fit' ? { ...single, mode, tracking: 'static' } : { ...single, mode }
}

export function cropWithTracking(crop: Crop, tracking: TrackingMode): Crop {
  return { ...crop, tracking: crop.mode === 'fill' ? tracking : 'static' }
}

export function framingNotices(framing: ExportFramingMetadata): string[] {
  const noSwitch = speakerSwitchCount(framing) === 0 ? 'Tidak ada perpindahan pembicara terdeteksi pada rentang ini. Tinjau preview untuk memastikan crop sesuai.' : null
  return [...new Set([framing.fallback_reason, noSwitch, ...(framing.warnings || [])].filter((message): message is string => typeof message === 'string' && message.trim().length > 0))]
}

export function speakerSwitchCount(framing: ExportFramingMetadata): number | null {
  return framing.mode === 'speaker' && Number.isInteger(framing.speaker_switches) && framing.speaker_switches! >= 0 ? framing.speaker_switches! : null
}

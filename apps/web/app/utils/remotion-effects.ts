import type { RemotionEffects, RemotionZoom } from '../types/api'

export function remotionEffects(value?: Partial<RemotionEffects>): RemotionEffects {
  return { transition_in: 'none', transition_out: 'none', transition_ms: 300, ...value,
    intro: { enabled: false, text: '', duration_ms: 1200, ...value?.intro },
    outro: { enabled: false, text: '', duration_ms: 1200, ...value?.outro },
    zooms: (value?.zooms || []).map(zoom => ({ ...zoom })) }
}
export function zoomAt(timeMs: number, durationMs: number): RemotionZoom {
  const start = Math.max(0, Math.min(Math.round(timeMs), durationMs - 100))
  return { start_ms: start, end_ms: Math.min(durationMs, start + 1500), scale: 1.2, x: .5, y: .5 }
}
export function intervalDrag<T extends { start_ms: number; end_ms: number }>(value: T, delta: number, duration: number, edge: 'move' | 'start' | 'end'): T {
  const minimum = Math.min(100, value.end_ms - value.start_ms)
  const shift = Math.round(delta / 10) * 10
  if (edge === 'start') return { ...value, start_ms: Math.max(0, Math.min(value.end_ms - minimum, value.start_ms + shift)) }
  if (edge === 'end') return { ...value, end_ms: Math.min(duration, Math.max(value.start_ms + minimum, value.end_ms + shift)) }
  const start = Math.max(0, Math.min(duration - (value.end_ms - value.start_ms), value.start_ms + shift))
  return { ...value, start_ms: start, end_ms: start + value.end_ms - value.start_ms }
}
/** Keep effects attached to the same source moments when the clip is trimmed. */
export function retimeEffects(value: RemotionEffects | undefined, oldStart: number, newStart: number, newEnd: number): RemotionEffects | undefined {
  if (!value) return undefined
  const effects = remotionEffects(value)
  const duration = newEnd - newStart
  effects.zooms = effects.zooms.map(zoom => ({ ...zoom,
    start_ms: Math.max(0, oldStart + zoom.start_ms - newStart),
    end_ms: Math.min(duration, oldStart + zoom.end_ms - newStart),
  })).filter(zoom => zoom.end_ms > zoom.start_ms)
  return effects
}
export function effectsError(effects: RemotionEffects | undefined, duration: number): string {
  if (!effects) return ''
  for (const key of ['intro', 'outro'] as const) {
    const title = effects[key]
    if (title.enabled && !title.text.trim()) return `Isi teks ${key} terlebih dahulu.`
    if (Array.from(title.text).length > 80) return `Teks ${key} maksimal 80 karakter.`
    if (title.duration_ms < 300 || title.duration_ms > 5000) return `Durasi ${key} harus 0,3–5 detik.`
  }
  if (effects.zooms.length > 20) return 'Maksimal 20 efek zoom per klip.'
  if (effects.zooms.some(zoom => ![zoom.start_ms, zoom.end_ms, zoom.scale, zoom.x, zoom.y].every(Number.isFinite) || zoom.start_ms < 0 || zoom.end_ms > duration || zoom.end_ms <= zoom.start_ms || zoom.scale < 1 || zoom.scale > 2 || zoom.x < 0 || zoom.x > 1 || zoom.y < 0 || zoom.y > 1)) return 'Periksa rentang dan kekuatan zoom: waktunya harus berada di dalam klip, dengan skala 1–2×.'
  return ''
}

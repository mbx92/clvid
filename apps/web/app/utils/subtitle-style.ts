import type { SubtitleStyle } from '../types/api'

export const subtitleDefaults = { renderer: 'ffmpeg' as const, remotion_template: 'gaming' as const, auto_fit: true, bold: false, italic: false, uppercase: false,
  text_color: '#FFFFFF', outline_color: '#111111', outline_width: 2.5, shadow: 0, background_color: '#000000',
  animation: 'none' as const, animation_ms: 180 }

/** Full reference template: unlike typography presets, this opts into Remotion. */
export const podcastSubtitlePreset = {
  name: 'Podcast kuning',
  style: { ...subtitleDefaults, enabled: true, renderer: 'remotion' as const, remotion_template: 'podcast' as const,
    display_mode: 'sentence' as const, background: false, text_color: '#FFE600', outline_color: '#111111',
    bold: true, italic: true, uppercase: true, outline_width: 6, shadow: 2,
    font_size: 64, auto_fit: false, position: 'bottom' as const, safe_margin: .16 },
}
export const subtitlePresets = [
  { name: 'Sinematik', color: '#FFF3D6', background: '#252A31', style: { ...subtitleDefaults, display_mode: 'sentence' as const, background: false, text_color: '#FFF3D6', outline_width: 1.5, shadow: 2, font_size: 46, animation: 'fade' as const, animation_ms: 300 } },
  { name: 'Gaming impact', color: '#FFE600', background: '#29282D', style: { ...subtitleDefaults, display_mode: 'sentence' as const, background: false, text_color: '#FFE600', bold: true, uppercase: true, outline_width: 5, shadow: 3, font_size: 68, animation: 'pop' as const, animation_ms: 160 } },
  { name: 'Komedi pop', color: '#FF95D8', background: '#352A42', style: { ...subtitleDefaults, display_mode: 'sentence' as const, background: false, text_color: '#FF95D8', bold: true, outline_width: 4, shadow: 2, font_size: 62, animation: 'rise' as const, animation_ms: 220 } },
  { name: 'Klasik', color: '#FFFFFF', background: '#252525', style: { ...subtitleDefaults, background: true, font_size: 52 } },
  { name: 'Bold putih', color: '#FFFFFF', background: '#425060', style: { ...subtitleDefaults, background: false, bold: true, outline_width: 5, font_size: 68 } },
  { name: 'Kuning', color: '#FFE600', background: '#29282D', style: { ...subtitleDefaults, background: false, text_color: '#FFE600', bold: true, uppercase: true, outline_width: 5, font_size: 68 } },
  { name: 'Neon', color: '#71FF5B', background: '#18322D', style: { ...subtitleDefaults, background: false, text_color: '#71FF5B', bold: true, outline_width: 4, shadow: 4, font_size: 64 } },
  { name: 'Kotak pop', color: '#FFFFFF', background: '#A02071', style: { ...subtitleDefaults, background: true, background_color: '#A02071', bold: true, font_size: 60 } },
  { name: 'Minimal', color: '#FFFFFF', background: '#4B5563', style: { ...subtitleDefaults, background: false, outline_width: 1, shadow: 3, font_size: 44 } },
]

/** Typography presets must not change the renderer or the selected Remotion motion. */
export function applySubtitlePreset(style: SubtitleStyle, preset: Partial<SubtitleStyle>): SubtitleStyle {
  return { ...subtitleDefaults, ...style, ...preset, enabled: true,
    renderer: style.renderer ?? subtitleDefaults.renderer,
    remotion_template: style.remotion_template ?? subtitleDefaults.remotion_template }
}

/** All sizes use the portrait container width, just like ASS at 1080px. */
export function captionAppearance(style: SubtitleStyle) {
  const s = { ...subtitleDefaults, ...style }
  return { color: s.text_color, fontWeight: s.bold ? '700' : '400', fontStyle: s.italic ? 'italic' : 'normal', fontSynthesis: 'weight style',
    backgroundColor: s.background ? `${s.background_color}b7` : 'transparent',
    padding: s.background ? `${8 / 10.8}cqw` : '0',
    WebkitTextStroke: s.background ? '0px' : `${s.outline_width / 10.8}cqw ${s.outline_color}`,
    paintOrder: 'stroke fill', textShadow: s.shadow ? `${s.shadow / 10.8}cqw ${s.shadow / 10.8}cqw 0 #0008` : 'none' }
}

/** A pure video-time animation, so scrubbing and pausing match the ASS export. */
export function captionMotion(style: SubtitleStyle, elapsedMs: number, durationMs: number) {
  const effect = style.animation || 'none'
  const origin = style.position === 'top' ? 'center top' : 'center bottom'
  if (effect === 'none' || durationMs <= 0) return { opacity: 1, transform: 'translateX(-50%)', transformOrigin: origin }
  const enter = Math.max(1, Math.min(style.animation_ms || 180, Math.floor(durationMs / 3)))
  const exit = Math.max(1, Math.min(enter, 150))
  const fadeIn = effect === 'pop' ? Math.min(enter, 60) : enter
  const elapsed = Math.max(0, elapsedMs)
  const opacity = Math.max(0, Math.min(1, elapsed / fadeIn, (durationMs - elapsed) / exit))
  const progress = Math.min(1, elapsed / enter)
  const scale = effect === 'pop' ? .85 + .15 * progress : 1
  const offset = effect === 'rise' ? (style.position === 'top' ? -1 : 1) * 24 * (1 - progress) / 10.8 : 0
  return { opacity, transform: `translateX(-50%) translateY(${offset}cqw) scale(${scale})`, transformOrigin: origin }
}

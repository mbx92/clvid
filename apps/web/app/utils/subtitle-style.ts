import type { SubtitleStyle } from '../types/api'

export const subtitleDefaults = { auto_fit: true, bold: false, italic: false, uppercase: false,
  text_color: '#FFFFFF', outline_color: '#111111', outline_width: 2.5, shadow: 0, background_color: '#000000' }
export const subtitlePresets = [
  { name: 'Klasik', color: '#FFFFFF', background: '#252525', style: { ...subtitleDefaults, background: true, font_size: 52 } },
  { name: 'Bold putih', color: '#FFFFFF', background: '#425060', style: { ...subtitleDefaults, background: false, bold: true, outline_width: 5, font_size: 68 } },
  { name: 'Kuning', color: '#FFE600', background: '#29282D', style: { ...subtitleDefaults, background: false, text_color: '#FFE600', bold: true, uppercase: true, outline_width: 5, font_size: 68 } },
  { name: 'Neon', color: '#71FF5B', background: '#18322D', style: { ...subtitleDefaults, background: false, text_color: '#71FF5B', bold: true, outline_width: 4, shadow: 4, font_size: 64 } },
  { name: 'Kotak pop', color: '#FFFFFF', background: '#A02071', style: { ...subtitleDefaults, background: true, background_color: '#A02071', bold: true, font_size: 60 } },
  { name: 'Minimal', color: '#FFFFFF', background: '#4B5563', style: { ...subtitleDefaults, background: false, outline_width: 1, shadow: 3, font_size: 44 } },
]

/** All sizes use the portrait container width, just like ASS at 1080px. */
export function captionAppearance(style: SubtitleStyle) {
  const s = { ...subtitleDefaults, ...style }
  return { color: s.text_color, fontWeight: s.bold ? '700' : '400', fontStyle: s.italic ? 'italic' : 'normal',
    backgroundColor: s.background ? `${s.background_color}b7` : 'transparent',
    padding: s.background ? `${8 / 10.8}cqw` : '0',
    WebkitTextStroke: s.background ? '0px' : `${s.outline_width / 10.8}cqw ${s.outline_color}`,
    paintOrder: 'stroke fill', textShadow: s.shadow ? `${s.shadow / 10.8}cqw ${s.shadow / 10.8}cqw 0 #0008` : 'none' }
}

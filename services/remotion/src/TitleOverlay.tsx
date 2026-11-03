import {AbsoluteFill} from 'remotion';
import {titleAtTime} from './effects';
import type {SubtitleStyle} from './types';

export function TitleOverlay({style, timeMs, durationMs, width}: {style: SubtitleStyle; timeMs: number; durationMs: number; width: number}) {
  const active = titleAtTime(style.remotion_effects, timeMs, durationMs);
  if (!active) return null;
  const scale = width / 1080;
  const text = style.uppercase ? active.title.text.toUpperCase() : active.title.text;
  return <AbsoluteFill style={{pointerEvents: 'none', justifyContent: 'center', alignItems: 'center', opacity: active.opacity}}>
    <div style={{width: '84%', boxSizing: 'border-box', padding: `${40 * scale}px ${32 * scale}px`, borderRadius: 16 * scale,
      transform: `translateY(${active.y * scale}px)`,
      background: `linear-gradient(135deg, #000000e8, ${style.background_color}ce)`,
      borderTop: `${3 * scale}px solid ${style.text_color}88`,
      boxShadow: `0 ${16 * scale}px ${48 * scale}px #0006`,
      color: style.text_color, fontFamily: '"Clipper Noto Sans", sans-serif',
      fontSize: Math.max(72, Math.min(112, style.font_size * 1.6)) * scale,
      fontWeight: 700, fontStyle: style.italic ? 'italic' : 'normal', fontSynthesis: 'weight style',
      lineHeight: 1.16, textAlign: 'center', whiteSpace: 'normal', overflowWrap: 'anywhere',
      textShadow: `${2 * scale}px ${3 * scale}px ${8 * scale}px ${style.outline_color}`,
    }}>{text}</div>
  </AbsoluteFill>;
}

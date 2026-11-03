import {defaultEffects, type RemotionEffects, type TitleEffect} from './types';

const clamp = (value: number) => Math.max(0, Math.min(1, value));
const smooth = (value: number) => {const t = clamp(value); return t * t * (3 - 2 * t);};

/** Pure clip-time motion shared by the native Vue video layer and MP4 scene. */
export function videoMotion(effects: RemotionEffects | undefined, timeMs: number, durationMs: number) {
  const e = effects ?? defaultEffects;
  const time = Math.max(0, Math.min(durationMs, Number.isFinite(timeMs) ? timeMs : 0));
  const transitionMs = Math.max(1, Math.min(e.transition_ms, durationMs / 2));
  const entering = smooth(time / transitionMs);
  const leaving = smooth((durationMs - time) / transitionMs);
  const opacity = Math.min(e.transition_in === 'none' ? 1 : entering, e.transition_out === 'none' ? 1 : leaving);
  const xPercent = (e.transition_in === 'slide' ? (1 - entering) * 6 : 0) - (e.transition_out === 'slide' ? (1 - leaving) * 6 : 0);
  let scale = 1, originX = .5, originY = .5;
  for (const zoom of e.zooms) {
    if (time < zoom.start_ms || time >= zoom.end_ms) continue;
    const ramp = Math.max(1, Math.min(250, (zoom.end_ms - zoom.start_ms) / 2));
    const envelope = Math.min(smooth((time - zoom.start_ms) / ramp), smooth((zoom.end_ms - time) / ramp));
    const currentScale = 1 + (zoom.scale - 1) * envelope;
    if (currentScale > scale) {scale = currentScale; originX = zoom.x; originY = zoom.y;}
  }
  return {opacity, transform: `translateX(${xPercent}%) scale(${scale})`, transformOrigin: `${originX * 100}% ${originY * 100}%`};
}

export interface ActiveTitle {title: TitleEffect; startMs: number; endMs: number; opacity: number; y: number}

/** Outro takes precedence if the two overlays overlap on a short clip. */
export function titleAtTime(effects: RemotionEffects | undefined, timeMs: number, durationMs: number): ActiveTitle | null {
  if (!effects || timeMs < 0 || timeMs >= durationMs) return null;
  let title: TitleEffect | undefined, startMs = 0, endMs = durationMs;
  const outroStart = Math.max(0, durationMs - effects.outro.duration_ms);
  if (effects.outro.enabled && effects.outro.text.trim() && timeMs >= outroStart) {
    title = effects.outro; startMs = outroStart;
  } else if (effects.intro.enabled && effects.intro.text.trim() && timeMs < Math.min(durationMs, effects.intro.duration_ms)) {
    title = effects.intro; endMs = Math.min(durationMs, effects.intro.duration_ms);
  }
  if (!title) return null;
  const ramp = Math.max(1, Math.min(240, (endMs - startMs) / 3));
  const entrance = smooth((timeMs - startMs) / ramp);
  const exit = smooth((endMs - timeMs) / ramp);
  return {title, startMs, endMs, opacity: Math.min(entrance, exit), y: 20 * (1 - entrance)};
}

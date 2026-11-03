import {spring} from 'remotion';
import type {Cue, SubtitleStyle} from './types';

export const frameCount = (durationMs: number, fps: number) => Math.max(1, Math.ceil(durationMs * fps / 1000));
export const clampFrame = (frame: number, durationMs: number, fps: number) => Math.max(0, Math.min(frameCount(durationMs, fps) - 1, Math.floor(Number.isFinite(frame) ? frame : 0)));

/** Cue ends are exclusive: no doubled caption at a word/cue boundary. */
export function cueAtFrame(cues: Cue[], frame: number, fps: number): Cue | undefined {
  const timeMs = frame * 1000 / fps;
  let selected: Cue | undefined;
  for (const cue of cues) {
    if (cue.start_ms <= timeMs && timeMs < cue.end_ms && (!selected || cue.start_ms < selected.start_ms)) selected = cue;
  }
  return selected;
}

export function captionMotion(style: SubtitleStyle, elapsedMs: number, durationMs: number, fps: number) {
  const elapsed = Math.max(0, elapsedMs);
  const requested = style.remotion_template === 'gaming' ? 180 : style.remotion_template === 'cinematic' ? 300 : style.animation_ms;
  const enter = Math.max(1, Math.min(requested, Math.floor(durationMs / 3)));
  const exit = Math.max(1, Math.min(enter, 150));
  const progress = Math.min(1, elapsed / enter);
  const fade = (fadeIn: number) => Math.max(0, Math.min(1, elapsed / fadeIn, (durationMs - elapsed) / exit));
  const direction = style.position === 'top' ? -1 : 1;
  if (style.remotion_template === 'gaming') {
    const bounce = spring({frame: elapsed * fps / 1000, fps, durationInFrames: Math.max(1, Math.ceil(enter * fps / 1000)), config: {damping: 11, stiffness: 180, mass: .7}});
    return {opacity: fade(Math.min(enter, 60)), scale: .76 + .24 * bounce, y: direction * 18 * (1 - bounce)};
  }
  if (style.remotion_template === 'cinematic') {
    const eased = 1 - Math.pow(1 - progress, 3);
    return {opacity: fade(enter), scale: .98 + .02 * eased, y: direction * 18 * (1 - eased)};
  }
  if (style.animation === 'none') return {opacity: 1, scale: 1, y: 0};
  return {
    opacity: fade(style.animation === 'pop' ? Math.min(enter, 60) : enter),
    scale: style.animation === 'pop' ? .85 + .15 * progress : 1,
    y: style.animation === 'rise' ? direction * 24 * (1 - progress) : 0,
  };
}

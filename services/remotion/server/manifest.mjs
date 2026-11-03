import {lstat, realpath, open} from 'node:fs/promises';
import path from 'node:path';

export class RenderInputError extends Error {
  constructor(code) {super(code); this.code = code;}
}
const reject = () => {throw new RenderInputError('invalid_manifest');};
const number = (value, low, high, integer = false) => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < low || value > high || (integer && !Number.isInteger(value))) reject();
  return value;
};
const enumeration = (value, options) => {if (!options.includes(value)) reject(); return value;};
const boolean = value => {if (typeof value !== 'boolean') reject(); return value;};
const color = value => {if (typeof value !== 'string' || !/^#[a-f\d]{6}$/i.test(value)) reject(); return value;};
const object = value => {if (!value || typeof value !== 'object' || Array.isArray(value)) reject(); return value;};

export function normalizeEffects(input, durationMs) {
  const e = input === undefined ? {} : object(input);
  const title = value => {
    const t = value === undefined ? {} : object(value);
    const enabled = boolean(t.enabled ?? false);
    const text = t.text ?? '';
    if (typeof text !== 'string' || Array.from(text).length > 80 || /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(text) || (enabled && !text.trim())) reject();
    return {enabled, text, duration_ms: number(t.duration_ms ?? 1200, 300, 5000, true)};
  };
  const inputZooms = e.zooms ?? [];
  if (!Array.isArray(inputZooms) || inputZooms.length > 20) reject();
  const zooms = inputZooms.map(item => {
    const z = object(item);
    const start_ms = number(z.start_ms, 0, durationMs, true);
    const end_ms = number(z.end_ms, 0, durationMs, true);
    if (end_ms <= start_ms) reject();
    return {start_ms, end_ms, scale: number(z.scale ?? 1.2, 1, 2), x: number(z.x ?? .5, 0, 1), y: number(z.y ?? .5, 0, 1)};
  });
  return {
    transition_in: enumeration(e.transition_in ?? 'none', ['none', 'fade', 'slide']),
    transition_out: enumeration(e.transition_out ?? 'none', ['none', 'fade', 'slide']),
    transition_ms: number(e.transition_ms ?? 300, 100, 1000, true),
    intro: title(e.intro), outro: title(e.outro), zooms,
  };
}

export function normalizeStyle(input, durationMs) {
  const s = object(input);
  // Construct a fresh allowlisted object; input cannot inject URLs or CSS.
  return {
    renderer: enumeration(s.renderer, ['remotion']),
    remotion_template: enumeration(s.remotion_template ?? 'gaming', ['minimal', 'gaming', 'cinematic']),
    remotion_effects: normalizeEffects(s.remotion_effects, durationMs),
    enabled: boolean(s.enabled ?? true),
    display_mode: enumeration(s.display_mode ?? 'sentence', ['sentence', 'words']),
    animation: enumeration(s.animation ?? 'none', ['none', 'fade', 'pop', 'rise']),
    animation_ms: number(s.animation_ms ?? 180, 100, 500, true),
    font_size: number(s.font_size ?? 52, 24, 100, true),
    position: enumeration(s.position ?? 'bottom', ['top', 'bottom']),
    background: boolean(s.background ?? true),
    safe_margin: number(s.safe_margin ?? .15, .05, .35),
    auto_fit: boolean(s.auto_fit ?? true), bold: boolean(s.bold ?? false),
    italic: boolean(s.italic ?? false), uppercase: boolean(s.uppercase ?? false),
    text_color: color(s.text_color ?? '#FFFFFF'), outline_color: color(s.outline_color ?? '#111111'),
    background_color: color(s.background_color ?? '#000000'),
    outline_width: number(s.outline_width ?? 2.5, 0, 8), shadow: number(s.shadow ?? 0, 0, 8),
  };
}

export function normalizeManifest(input) {
  const m = object(input);
  if (m.version !== 1) reject();
  const durationMs = number(m.durationMs, 1, 1800000, true);
  const width = enumeration(m.width, [720, 1080]);
  const height = width === 720 ? 1280 : 1920;
  if (m.height !== height || m.fps !== 30) reject();
  if (!Array.isArray(m.cues) || m.cues.length > 10000) reject();
  let textLength = 0;
  const cues = m.cues.map(item => {
    const c = object(item);
    const start_ms = number(c.start_ms, 0, durationMs, true);
    const end_ms = number(c.end_ms, 0, durationMs, true);
    if (end_ms <= start_ms || typeof c.text !== 'string' || !c.text.trim() || Array.from(c.text).length > 2000 || /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(c.text)) reject();
    textLength += Array.from(c.text).length;
    if (textLength > 1000000) reject();
    return {start_ms, end_ms, text: c.text};
  }).sort((a, b) => a.start_ms - b.start_ms);
  for (const field of ['videoPath', 'outputPath']) {
    if (typeof m[field] !== 'string' || !m[field] || m[field].length > 4096 || m[field].includes('\0') || /^[a-z]+:\/\//i.test(m[field]) || m[field].split(/[\\/]/).includes('..')) reject();
  }
  return {version: 1, videoPath: m.videoPath, outputPath: m.outputPath, durationMs, width, height, fps: 30, cues, style: normalizeStyle(m.style, durationMs)};
}

export function isWithin(root, target) {
  const relative = path.relative(root, target);
  return relative !== '' && relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}

export async function readManifest(manifestPath) {
  try {
    const resolvedManifest = await realpath(path.resolve(manifestPath));
    const root = path.dirname(resolvedManifest);
    const handle = await open(resolvedManifest, 'r');
    let raw;
    try {
      const stat = await handle.stat();
      if (!stat.isFile() || stat.size < 2 || stat.size > 2 * 1024 * 1024) reject();
      // A fixed buffer bounds reads even if a concurrent writer grows the file.
      const buffer = Buffer.alloc(stat.size + 1);
      const {bytesRead} = await handle.read(buffer, 0, buffer.length, 0);
      if (bytesRead !== stat.size) reject();
      raw = JSON.parse(buffer.subarray(0, bytesRead).toString('utf8'));
    } finally {await handle.close();}
    const manifest = normalizeManifest(raw);
    const video = path.resolve(root, manifest.videoPath);
    const output = path.resolve(root, manifest.outputPath);
    if (!isWithin(root, video) || !isWithin(root, output) || path.extname(video).toLowerCase() !== '.mp4' || path.extname(output).toLowerCase() !== '.mp4' || video === output) reject();
    const canonicalVideo = await realpath(video);
    const canonicalOutputParent = await realpath(path.dirname(output));
    if (!isWithin(root, canonicalVideo) || !(canonicalOutputParent === root || isWithin(root, canonicalOutputParent))) reject();
    const outputPath = path.join(canonicalOutputParent, path.basename(output));
    const videoStat = await lstat(canonicalVideo);
    if (!videoStat.isFile() || videoStat.size < 1 || videoStat.size > 8 * 1024 ** 3) reject();
    try {await lstat(outputPath); reject();} catch (error) {if (error.code !== 'ENOENT') throw error;}
    return {...manifest, videoPath: canonicalVideo, outputPath, root};
  } catch (error) {
    if (error instanceof RenderInputError) throw error;
    throw new RenderInputError('invalid_manifest');
  }
}

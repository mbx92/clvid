import {readFile, realpath, stat} from 'node:fs/promises';
import {resolve, dirname, basename} from 'node:path';
import {RenderInputError} from './manifest.mjs';
const reject = () => {throw new RenderInputError('invalid_story_manifest');};
export function validateStoryCaptions(s) {
  if (s.caption_audio_id !== undefined && s.caption_audio_id !== null && (typeof s.caption_audio_id !== 'string' || s.caption_audio_id.length > 36)) reject();
  if (s.caption_narration !== undefined && (typeof s.caption_narration !== 'string' || Array.from(s.caption_narration).length > 600)) reject();
  if (s.captions === undefined) return;
  if (!Array.isArray(s.captions) || s.captions.length > 200) reject();
  let end = 0;
  for (const cue of s.captions) {
    if (!cue || typeof cue !== 'object' || Array.isArray(cue) || Object.keys(cue).some(k => !['start_ms','end_ms','text'].includes(k))) reject();
    if (!Number.isInteger(cue.start_ms) || !Number.isInteger(cue.end_ms) || cue.start_ms < end || cue.end_ms <= cue.start_ms || cue.end_ms > s.duration_ms) reject();
    if (typeof cue.text !== 'string' || !cue.text.trim() || Array.from(cue.text).length > 200) reject();
    end = cue.end_ms;
  }
}
export function validateStoryVisual(v) {
  if (!v || typeof v !== 'object' || Array.isArray(v) || Object.keys(v).some(k => !['kind','items','motion','reveal_ms'].includes(k))) reject();
  if (!['none','coffee_compare','coffee_flat','coffee_pair','coffee_separate','coffee_peaberry','coffee_reveal','diagram','comparison','steps'].includes(v.kind)) reject();
  if (!['gentle','still'].includes(v.motion) || !Number.isInteger(v.reveal_ms) || v.reveal_ms < 0 || v.reveal_ms > 10000) reject();
  if (!Array.isArray(v.items) || v.items.length > 4) reject();
  for (const item of v.items) {
    if (!item || Object.keys(item).some(k => !['icon','label'].includes(k)) || !['bean','cup','leaf','water','sun','person','box','check','question'].includes(item.icon) || typeof item.label !== 'string' || Array.from(item.label).length > 32) reject();
  }
}
export async function readStoryManifest(file) {
  try {
    const root = await realpath(dirname(resolve(file)));
    if ((await stat(file)).size > 2 * 1024 * 1024) reject();
    const m = JSON.parse(await readFile(file, 'utf8'));
    if (m.version !== 1 || m.fps !== 30 || ![[720,1280],[1280,720],[1080,1080]].some(([w,h]) => m.width === w && m.height === h)) reject();
    const doc = m.document, theme = doc.theme;
    for (const color of ['background', 'foreground', 'accent']) if (!/^#[a-f0-9]{6}$/i.test(theme[color])) reject();
    if (!['sans','serif','mono'].includes(theme.font) || !['rise','fade','zoom','none'].includes(theme.motion) || !['left','center'].includes(theme.align) || !Number.isInteger(theme.font_size) || theme.font_size < 40 || theme.font_size > 100 || typeof theme.uppercase !== 'boolean') reject();
    if (!Array.isArray(doc.scenes) || doc.scenes.length < 1 || doc.scenes.length > 20) reject();
    let durationMs = 0;
    for (const s of doc.scenes) {
      if (s.visual !== undefined) validateStoryVisual(s.visual);
      if (!['title','split','quote','stat'].includes(s.layout) || typeof s.id !== 'string') reject();
      if (!Number.isInteger(s.duration_ms) || s.duration_ms < 1000 || s.duration_ms > 30000 || s.duration_ms % 100) reject();
      validateStoryCaptions(s);
      if (!Number.isInteger(s.media_start_ms) || s.media_start_ms < 0 || s.media_start_ms > 180000 || typeof s.show_caption !== 'boolean') reject();
      for (const [key, max] of [['title',120],['text',360],['narration',600]]) if (typeof s[key] !== 'string' || Array.from(s[key]).length > max) reject();
      durationMs += s.duration_ms;
      for (const key of ['asset_id','audio_id']) {
        if (s[key] !== null && (typeof s[key] !== 'string' || s[key].length > 36)) reject();
        if (s[key] && (!m.assets[s[key]] || !(key === 'audio_id' ? ['audio'] : ['image','video']).includes(m.assets[s[key]].kind))) reject();
      }
    }
    if (durationMs > 180000 || new Set(doc.scenes.map(s => s.id)).size !== doc.scenes.length || Object.keys(m.assets).length > 40) reject();
    for (const asset of Object.values(m.assets)) {
      if (!['image','video','audio'].includes(asset.kind) || !['image/png','video/mp4','audio/mp4'].includes(asset.mime)) reject();
      asset.path = await realpath(asset.path);
      if (dirname(asset.path) !== root || !(await stat(asset.path)).isFile()) reject();
    }
    const outputPath = resolve(m.outputPath);
    if (dirname(outputPath) !== root || !basename(outputPath).endsWith('.mp4') || Object.values(m.assets).some(a => a.path === outputPath)) reject();
    return {...m, outputPath, durationMs};
  } catch (e) {if (e instanceof RenderInputError) throw e; reject();}
}

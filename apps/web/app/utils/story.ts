import type { Asset, Job } from '~/types/api'
export interface StoryTheme { background: string; foreground: string; accent: string; font: 'sans'|'serif'|'mono'; motion: 'fade'|'rise'|'zoom'|'none'; align: 'left'|'center'; font_size: number; uppercase: boolean }
export interface StoryVisual {kind: string; items: {icon:string;label:string}[]; motion:'gentle'|'still'; reveal_ms:number}
export const emptyVisual = (): StoryVisual => ({kind:'none',items:[],motion:'gentle',reveal_ms:2000})
export const visualOptions = [{value:'none',label:'Tanpa ilustrasi'},{value:'coffee_compare',label:'Kopi: tebak biji A / B'},{value:'coffee_flat',label:'Kopi: sisi rata'},{value:'coffee_pair',label:'Kopi: penampang dua biji'},{value:'coffee_separate',label:'Kopi: pisahkan dua biji'},{value:'coffee_peaberry',label:'Kopi: satu biji peaberry'},{value:'coffee_reveal',label:'Kopi: ungkap jawaban B'},{value:'diagram',label:'Diagram objek'},{value:'comparison',label:'Perbandingan'},{value:'steps',label:'Alur langkah'}]
export const visualIcons = [{value:'bean',label:'Biji kopi'},{value:'cup',label:'Cangkir'},{value:'leaf',label:'Daun'},{value:'water',label:'Air'},{value:'sun',label:'Matahari'},{value:'person',label:'Orang'},{value:'box',label:'Kotak'},{value:'check',label:'Centang'},{value:'question',label:'Pertanyaan'}]
export interface StoryCaption { start_ms: number; end_ms: number; text: string }
export interface StoryScene { id: string; layout: 'title'|'split'|'quote'|'stat'; title: string; text: string; narration: string; visual_note: string; visual: StoryVisual; duration_ms: number; asset_id: string|null; audio_id: string|null; media_start_ms: number; show_caption: boolean; captions: StoryCaption[]; caption_audio_id: string|null; caption_narration: string }
export interface StoryDocument { title: string; script: string; style_prompt: string; preserve_script: boolean; aspect: 'portrait'|'landscape'|'square'; theme: StoryTheme; scenes: StoryScene[] }
export type StoryProduceMode = 'images'|'speech'|'captions'|'complete'
export interface StoryCapabilities { images: boolean; speech: boolean; alignment: boolean; voices: string[]; default_voice: string; voice_labels?: Record<string,string>; provider?: 'local'|'openai' }
export const storyVoiceLabel = (voice: string, capabilities?: StoryCapabilities) => capabilities?.voice_labels?.[voice] || ({'id_ID-news_tts-medium':'Bahasa Indonesia — News', 'en_US-lessac-medium':'Bahasa Inggris — Lessac'}[voice] || voice)
export function storyProviderNotice(capabilities?: StoryCapabilities) {
  if (capabilities?.images && capabilities?.speech) return ''
  const subject = !capabilities?.images && !capabilities?.speech ? 'gambar dan suara' : !capabilities?.images ? 'gambar' : 'suara'
  if (capabilities?.provider === 'local') return `Model ${subject} lokal belum siap. Selesaikan pemasangan model di server, lalu muat ulang halaman. Anda tetap dapat mengunggah aset dan membuat subtitle dari rekaman.`
  return `${!capabilities?.images && !capabilities?.speech ? 'Layanan gambar AI dan suara narator' : !capabilities?.images ? 'Layanan gambar AI' : 'Layanan suara narator'} belum aktif. Anda tetap dapat mengunggah aset dan membuat subtitle dari rekaman.`
}
export interface StoryJob extends Omit<Job, 'result_json'> { result_json?: {document?: StoryDocument; base_version?: number; mode?: string; mp4_asset_id?: string; srt_asset_id?: string; version?: number; warnings?: string[]} }
export interface StoryDetail { id: string; version: number; document: StoryDocument; assets: Asset[]; jobs: StoryJob[]; ai_available: boolean; capabilities?: StoryCapabilities }
export interface StoryTemplate { id: string; name: string; theme: StoryTheme; custom?: boolean }
export const storyTheme = (): StoryTheme => ({background: '#132923', foreground: '#FFFFFF', accent: '#D9F279', font: 'sans', motion: 'rise', align: 'left', font_size: 72, uppercase: false})
export const newScene = (): StoryScene => ({id: crypto.randomUUID(), layout: 'title', title: 'Adegan baru', text: '', narration: '', visual_note: '', visual:emptyVisual(), duration_ms: 5000, asset_id: null, audio_id: null, media_start_ms: 0, show_caption: true, captions: [], caption_audio_id: null, caption_narration: ''})
export const normalizeStory = (doc:StoryDocument):StoryDocument => ({...doc,scenes:doc.scenes.map(s=>({...s,visual:{...emptyVisual(),...s.visual},captions:s.captions || [],caption_audio_id:s.caption_audio_id || null,caption_narration:s.caption_narration || ''}))})
export const hasTimedCaptions = (scene: StoryScene) => !!scene.audio_id && !!scene.captions?.length && scene.caption_audio_id === scene.audio_id && scene.caption_narration === scene.narration
export const storyModeLabel = (mode?: string) => ({storyboard:'storyboard',style:'gaya',visuals:'ilustrasi',images:'gambar AI',speech:'suara narator',captions:'subtitle dari audio',complete:'produksi video'}[mode || 'storyboard'] || 'storyboard')
export const newStory = (): StoryDocument => ({title: 'Video baru', script: '', style_prompt: '', preserve_script: true, aspect: 'portrait', theme: storyTheme(), scenes: [newScene()]})
export const storySize = (aspect: StoryDocument['aspect']) => ({portrait: [720,1280], landscape: [1280,720], square: [1080,1080]}[aspect]!)
export function storyError(d: StoryDocument) {
  if (!d.title.trim()) return 'Isi judul video.'
  if (d.scenes.length < 1 || d.scenes.length > 20) return 'Gunakan 1 sampai 20 adegan.'
  if (d.scenes.reduce((sum, s) => sum + s.duration_ms, 0) > 180000) return 'Total durasi maksimal 3 menit.'
  if (d.scenes.some(s => !Number.isInteger(s.duration_ms) || s.duration_ms < 1000 || s.duration_ms > 30000 || s.duration_ms % 100)) return 'Durasi tiap adegan 1–30 detik, dengan kelipatan 0,1 detik.'
  if (!Number.isInteger(d.theme.font_size) || d.theme.font_size < 40 || d.theme.font_size > 100) return 'Ukuran judul harus 40 sampai 100.'
  if (d.scenes.some(s => s.visual && (!Number.isInteger(s.visual.reveal_ms) || s.visual.reveal_ms < 0 || s.visual.reveal_ms > 10000))) return 'Waktu ungkap jawaban harus antara 0 dan 10 detik.'
  if (d.scenes.some(s => !Number.isInteger(s.media_start_ms) || s.media_start_ms < 0 || s.media_start_ms > 180000)) return 'Titik mulai video harus antara 0 dan 180 detik.'
  for (const [index, scene] of d.scenes.entries()) {
    const captions = scene.captions || []
    if (captions.length > 200 || captions.some(cue => [...cue.text].length > 200)) return `Subtitle adegan ${index+1} maksimal 200 cue, masing-masing 200 karakter.`
    if (captions.some((cue,i) => !cue.text.trim() || !Number.isInteger(cue.start_ms) || !Number.isInteger(cue.end_ms) || cue.start_ms < 0 || cue.end_ms <= cue.start_ms || cue.end_ms > scene.duration_ms || (i > 0 && cue.start_ms < captions[i-1]!.end_ms))) return `Periksa subtitle adegan ${index+1}: isi teks, urutkan waktunya, dan pastikan tidak melewati durasi adegan.`
  }
  return ''
}

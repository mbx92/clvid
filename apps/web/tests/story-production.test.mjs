import assert from 'node:assert/strict'
import test from 'node:test'
import {newStory, normalizeStory, hasTimedCaptions, storyError, storyProviderNotice, storyVoiceLabel} from '../app/utils/story.ts'

test('timed captions stay tied to both the chosen recording and exact narration', () => {
  const scene = newStory().scenes[0]
  Object.assign(scene, {audio_id:'audio-1',narration:'Kopi segar.',caption_audio_id:'audio-1',caption_narration:'Kopi segar.',captions:[{start_ms:300,end_ms:2400,text:'Kopi segar.'}]})
  assert.equal(hasTimedCaptions(scene),true)
  assert.equal(hasTimedCaptions({...scene,audio_id:'audio-2'}),false)
  assert.equal(hasTimedCaptions({...scene,narration:'Kopi baru.'}),false)
  assert.equal(hasTimedCaptions({...scene,audio_id:null,caption_audio_id:null}),false)
})

test('manual cue edits reject overlaps, blank text and shortening beyond the final cue', () => {
  const document = newStory(), scene = document.scenes[0]
  scene.captions = [{start_ms:300,end_ms:2400,text:'Kopi segar.'},{start_ms:3000,end_ms:4500,text:'Seduh perlahan.'}]
  assert.equal(storyError(document),'')
  scene.duration_ms = 4000
  assert.match(storyError(document),/Periksa subtitle adegan 1/)
  scene.duration_ms = 5000
  scene.captions[1].start_ms = 2300
  assert.match(storyError(document),/Periksa subtitle adegan 1/)
  scene.captions[1].start_ms = 3000
  scene.captions[1].text = ' '
  assert.match(storyError(document),/Periksa subtitle adegan 1/)
})

test('old story documents normalize without inventing aligned subtitle timings', () => {
  const document = newStory()
  for (const key of ['visual','captions','caption_audio_id','caption_narration']) delete document.scenes[0][key]
  const normalized = normalizeStory(document)
  assert.deepEqual(normalized.scenes[0].captions,[])
  assert.equal(hasTimedCaptions(normalized.scenes[0]),false)
  assert.equal(storyError(normalized),'')
})

test('local setup messages identify missing models without requiring cloud credentials', () => {
  const capabilities = {provider:'local',images:false,speech:true,alignment:true,voices:['id_ID-news_tts-medium'],default_voice:'id_ID-news_tts-medium'}
  assert.match(storyProviderNotice(capabilities), /Model gambar lokal belum siap/)
  assert.doesNotMatch(storyProviderNotice(capabilities), /OpenAI|kunci|API_KEY/)
  assert.equal(storyProviderNotice({...capabilities,images:true}), '')
  assert.match(storyVoiceLabel(capabilities.default_voice), /Bahasa Indonesia/)
  assert.equal(storyVoiceLabel('coral'), 'coral')
  assert.equal(storyVoiceLabel('custom-local', {...capabilities,voice_labels:{'custom-local':'Narator Indonesia'}}), 'Narator Indonesia')
  assert.match(storyProviderNotice({...capabilities,provider:'openai'}), /Layanan gambar AI belum aktif/)
})

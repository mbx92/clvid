import assert from 'node:assert/strict'
import test from 'node:test'
import { alignHighlightWords, alignWords } from '../app/utils/word-captions.ts'
import { readFileSync } from 'node:fs'

test('podcast highlight agrees with the server on timing, trimming, repeated words and missing data', () => {
  const fixtures = JSON.parse(readFileSync(new URL('../../../tests/fixtures/podcast-timing.json', import.meta.url), 'utf8'))
  for (const item of fixtures) {
    const original = JSON.stringify(item)
    const result = alignHighlightWords([item.cue], item.words, item.clip_start)
    assert.deepEqual(result.cues, [{ ...item.cue, word_spans: item.spans || [] }], item.name)
    assert.equal(result.missing, item.spans === null ? 1 : 0, item.name)
    assert.equal(JSON.stringify(item), original)
  }
})
test('word captions follow observed speech, leave silence and preserve display edits', () => {
  const words = [{ word:' Ini',start_ms:10500,end_ms:10900 }, { word:' momen',start_ms:11400,end_ms:11900 }, { word:' seru.',start_ms:12800,end_ms:13500 }]
  const cues = [{start_ms:0,end_ms:6000,text:'INI momen seru!'}]
  const result = alignWords(cues,words,10000)
  assert.equal(result.missing,0)
  assert.deepEqual(result.events,[{start_ms:500,end_ms:900,text:'INI'},{start_ms:1400,end_ms:1900,text:'momen'},{start_ms:2800,end_ms:3500,text:'seru!'}])
  assert.equal(result.events.find(e => e.start_ms <= 1100 && e.end_ms > 1100),undefined)
  assert.equal(alignWords([{...cues[0],text:'Teks berbeda'}],words,10000).missing,1)
  assert.deepEqual(alignWords(cues,[],10000),{events:[],missing:1})
  assert.deepEqual(alignWords([{start_ms:0,end_ms:1200,text:'Sama-sama New York!'}],
    [{word:' sama',start_ms:100,end_ms:300},{word:'-sama',start_ms:300,end_ms:600},{word:' New York',start_ms:800,end_ms:1000}],0),
    {missing:0,events:[{start_ms:100,end_ms:600,text:'Sama-sama'},{start_ms:800,end_ms:1000,text:'New York!'}]})
})

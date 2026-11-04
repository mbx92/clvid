import assert from 'node:assert/strict'
import test from 'node:test'
import {repairSubtitles} from '../app/utils/repair-subtitles.ts'
import {captionLayout} from '../app/utils/subtitles.ts'
import {alignHighlightWords} from '../app/utils/word-captions.ts'
const style={enabled:true,font_size:100,auto_fit:false,renderer:'remotion',remotion_template:'minimal',display_mode:'sentence'}
const text='Kopi tumbuh dalam buah merah dan setiap biji memiliki bentuk yang menarik untuk diperhatikan sebelum kita menggilingnya. '.repeat(4).trim()

test('auto fit alone fixes a large-font cue while preserving all text and time',()=>{
  const cues=[{start_ms:500,end_ms:3500,text:'Kopi ini tumbuh sendirian di dalam buah merah yang dipetik pagi tadi.'}]
  assert.equal(captionLayout(cues[0].text,100,false).tooLong,true)
  const result=repairSubtitles(cues,style,[],0)
  assert.deepEqual(result.cues,cues)
  assert.equal(result.style.auto_fit,true)
  assert.equal(result.splitCount,0)
})

test('long translated cues split without losing text and stay within their original time range',()=>{
  const cues=[{start_ms:250,end_ms:15250,text}, {start_ms:16000,end_ms:17000,text:'Penutup.'}]
  const original=JSON.stringify(cues)
  const result=repairSubtitles(cues,style,[],10000)
  assert.equal(result.estimatedCount,1)
  assert.equal(result.splitCount,1)
  assert.equal(result.cues[0].start_ms,250)
  assert.equal(result.cues.at(-2).end_ms,15250)
  assert.deepEqual(result.cues.at(-1),cues[1])
  assert.equal(result.cues.slice(0,-1).map(c=>c.text).join(' '),text)
  result.cues.forEach(c=>assert.equal(captionLayout(c.text,100,true).tooLong,false))
  result.cues.slice(0,-2).forEach((c,i)=>assert.equal(c.end_ms,result.cues[i+1].start_ms))
  assert.equal(JSON.stringify(cues),original)
})

test('podcast splitting uses observed word boundaries and retains correct highlights',()=>{
  const tokens=text.split(' ')
  const words=tokens.map((word,i)=>({word,start_ms:10000+100+i*200,end_ms:10000+250+i*200}))
  const cues=[{start_ms:0,end_ms:tokens.length*200+1000,text}]
  const result=repairSubtitles(cues,{...style,remotion_template:'podcast'},words,10000)
  assert.equal(result.estimatedCount,0)
  assert.equal(result.style.remotion_template,'podcast')
  assert.equal(alignHighlightWords(result.cues,words,10000).missing,0)
  for(const cue of result.cues.slice(1)) assert.ok(words.some(w=>w.start_ms-10000===cue.start_ms))
})

test('estimated timings never masquerade as podcast word timings',()=>{
  const result=repairSubtitles([{start_ms:0,end_ms:10000,text}],{...style,remotion_template:'podcast'},[],0)
  assert.equal(result.fallback,true)
  assert.equal(result.style.remotion_template,'minimal')
  assert.equal(result.style.display_mode,'sentence')
  assert.ok(result.cues.every(c=>!c.word_spans))
})

test('unbreakable words and impossibly short cues are reported without losing text',()=>{
  for(const cue of [{start_ms:0,end_ms:1000,text:'x'.repeat(300)}, {start_ms:0,end_ms:1,text}]) {
    const result=repairSubtitles([cue],style,[],0)
    assert.equal(result.unresolved,1)
    assert.deepEqual(result.cues,[cue])
  }
})

import type { Cue, SourceWord, SubtitleStyle } from '../types/api'
import { captionLayout } from './subtitles.ts'
import { alignHighlightWords } from './word-captions.ts'

/** Propose bounded captions; never truncate text or fabricate word timestamps. */
export function repairSubtitles(cues:Cue[], style:SubtitleStyle, words:SourceWord[], clipStart:number) {
  const fits = (text:string) => !captionLayout(style.uppercase ? text.toUpperCase() : text, style.font_size, true).tooLong
  let splitCount=0, estimatedCount=0, unresolved=0
  const output:Cue[]=[]
  for (const cue of cues) {
    if(fits(cue.text)) {output.push({...cue}); continue}
    const tokens=cue.text.trim().split(/\s+/u)
    const aligned=alignHighlightWords([cue],words,clipStart)
    const spans=aligned.missing ? [] : aligned.cues[0]!.word_spans!
    const units:{text:string;start:number}[]=[]
    if(spans.length) {
      let cursor=0
      spans.forEach((span,i)=>{
        const end=i===spans.length-1 ? tokens.length : span.end_word
        units.push({text:tokens.slice(cursor,end).join(' '),start:i===0?cue.start_ms:span.start_ms});cursor=end
      })
    } else tokens.forEach(text=>units.push({text,start:0}))
    if(units.some(u=>!fits(u.text))) {output.push({...cue});unresolved++;continue}
    const groups:{text:string;start:number}[]=[]
    for(const unit of units) {
      const last=groups.at(-1)
      if(last && fits(`${last.text} ${unit.text}`)) last.text+=` ${unit.text}`
      else groups.push({...unit})
    }
    const duration=cue.end_ms-cue.start_ms
    if(groups.length>duration || output.length+groups.length>2000) {output.push({...cue});unresolved++;continue}
    if(!spans.length) {
      const total=groups.reduce((n,g)=>n+Array.from(g.text).length,0)
      let weight=0
      groups.forEach(g=>{g.start=cue.start_ms+Math.floor(duration*weight/total);weight+=Array.from(g.text).length})
    }
    const parts=groups.map((g,i)=>({start_ms:g.start,end_ms:groups[i+1]?.start ?? cue.end_ms,text:g.text}))
    if(parts.some(p=>p.end_ms<=p.start_ms || p.start_ms<cue.start_ms || p.end_ms>cue.end_ms)) {output.push({...cue});unresolved++;continue}
    output.push(...parts);splitCount++;if(!spans.length) estimatedCount++
  }
  if(output.length>2000) throw new Error('Hasil melebihi batas 2.000 cue. Gunakan klip yang lebih pendek.')
  const nextStyle={...style,auto_fit:true}
  // Estimated sentence boundaries cannot support source-language karaoke.
  const podcast=style.renderer==='remotion' && style.remotion_template==='podcast'
  const fallback=estimatedCount>0 && (podcast || style.display_mode==='words')
  if(fallback) {if(podcast) nextStyle.remotion_template='minimal';nextStyle.display_mode='sentence'}
  return {cues:output,style:nextStyle,splitCount,estimatedCount,unresolved,fallback}
}

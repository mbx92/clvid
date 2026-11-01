import type { Cue, SourceWord } from '../types/api'
const normalized = (word: string) => word.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '')
export function alignWords(cues: Cue[], sourceWords: SourceWord[], clipStart: number) {
  const events: Cue[] = []
  let missing = 0
  for (const cue of cues) {
    const start = clipStart + cue.start_ms, end = clipStart + cue.end_ms
    const words = sourceWords.filter(w => w.end_ms > start && w.start_ms < end)
    const tokens = cue.text.trim().split(/\s+/u)
    if (!words.length || normalized(tokens.join('')) !== normalized(words.map(w => w.word).join(''))) {
      missing++; continue
    }
    const grouped: Cue[] = []
    let i = 0, j = 0, valid = true
    while (i < tokens.length && j < words.length) {
      const firstI = i, firstJ = j
      let written = normalized(tokens[i++]!), spoken = normalized(words[j++]!.word)
      while (written !== spoken && (i < tokens.length || j < words.length)) {
        if (written.length <= spoken.length && i < tokens.length) written += normalized(tokens[i++]!)
        else if (j < words.length) spoken += normalized(words[j++]!.word)
        else break
      }
      const group = words.slice(firstJ, j)
      const begin = Math.max(start, group[0]!.start_ms), finish = Math.min(end, group[group.length - 1]!.end_ms)
      if (!written || written !== spoken || finish <= begin ||
        group.some((w, k) => w.end_ms < w.start_ms || k > 0 && w.start_ms < group[k - 1]!.end_ms) ||
        grouped.length > 0 && begin - clipStart < grouped[grouped.length - 1]!.end_ms) { valid = false; break }
      grouped.push({ start_ms: begin - clipStart, end_ms: finish - clipStart, text: tokens.slice(firstI, i).join(' ') })
    }
    if (!valid || i !== tokens.length || j !== words.length) missing++
    else events.push(...grouped)
  }
  return { events, missing }
}

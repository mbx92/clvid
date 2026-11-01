export interface CaptionLayout { text: string; fontSize: number; tooLong: boolean }

/** Match app.media.subtitles: balanced two-line captions in the 80% safe width. */
export function captionLayout(input: string, requestedSize: number, autoFit = true): CaptionLayout {
  const text = input.trim().replace(/\s+/gu, ' ')
  const characters = Array.from(text)
  if (!autoFit) {
    const target = Math.max(1, Math.floor(864 / (requestedSize * .62)))
    const lines: string[] = []
    let line = ''
    for (const word of text.split(' ').filter(Boolean)) {
      let rest = Array.from(word)
      if (rest.length <= target) {
        if (line && Array.from(line).length + 1 + rest.length > target) { lines.push(line); line = '' }
        line += (line ? ' ' : '') + word
      } else {
        if (line) line += ' '
        while (rest.length) {
          const space = target - Array.from(line).length
          if (space <= 0) { lines.push(line.trimEnd()); line = ''; continue }
          line += rest.splice(0, space).join('')
          if (rest.length) { lines.push(line.trimEnd()); line = '' }
        }
      }
    }
    if (line) lines.push(line)
    return { text: lines.join('\n'), fontSize: requestedSize, tooLong: lines.length > 4 }
  }
  const target = Math.max(12, Math.floor(864 / (requestedSize * 0.55)))
  let lines = [text]
  if (characters.length > target) {
    const middle = characters.length / 2
    const spaces = characters.map((character, index) => character === ' ' ? index : -1).filter(index => index >= 0)
    const split = spaces.length ? spaces.reduce((best, value) => Math.abs(value - middle) < Math.abs(best - middle) ? value : best) : Math.ceil(middle)
    lines = [characters.slice(0, split).join('').trim(), characters.slice(split).join('').trim()]
  }
  const longest = Math.max(1, ...lines.map(line => Array.from(line).length))
  const fit = Math.min(requestedSize, Math.round(864 / (longest * 0.62)))
  return { text: lines.join('\n'), fontSize: Math.max(24, fit), tooLong: fit < 24 }
}

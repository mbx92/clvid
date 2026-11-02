export type ThumbnailFormat = 'landscape' | 'portrait' | 'square'
export type ThumbnailStyle = 'yellow' | 'white' | 'panel' | 'gradient' | 'neon' | 'pop'
export type ThumbnailPosition = 'top' | 'middle' | 'bottom'
export type ThumbnailPalette = 'sunset' | 'electric' | 'candy' | 'lime'
export type ThumbnailFont = 'display' | 'modern'

export const thumbnailStyles: { value: ThumbnailStyle; label: string; description: string }[] = [
  { value: 'pop', label: 'Pop 3D', description: 'Huruf tebal, gradasi, dan bayangan bertingkat' },
  { value: 'gradient', label: 'Gradasi', description: 'Gradasi cerah dengan outline gelap' },
  { value: 'neon', label: 'Neon', description: 'Teks putih dengan cahaya berwarna' },
  { value: 'yellow', label: 'Kuning tebal', description: 'Kuning klasik dengan outline hitam' },
  { value: 'white', label: 'Putih tebal', description: 'Putih klasik dengan outline hitam' },
  { value: 'panel', label: 'Putih dengan latar gelap', description: 'Teks putih di atas panel gelap' },
]
export const thumbnailPalettes: { value: ThumbnailPalette; label: string; colors: [string, string] }[] = [
  { value: 'sunset', label: 'Emas oranye', colors: ['#fff36b', '#ff831e'] },
  { value: 'electric', label: 'Biru ungu', colors: ['#67f4ff', '#a879ff'] },
  { value: 'candy', label: 'Pink ungu', colors: ['#ffb4ee', '#e544ff'] },
  { value: 'lime', label: 'Hijau limau', colors: ['#efff8a', '#54e969'] },
]

export function thumbnailSize(format: ThumbnailFormat): [number, number] {
  return format === 'portrait' ? [720, 1280] : format === 'square' ? [1080, 1080] : [1280, 720]
}

// A centered cover crop; fit keeps the complete image with a dark matte.
export function thumbnailPlacement(sw: number, sh: number, width: number, height: number, fit: boolean) {
  if (![sw, sh, width, height].every(n => Number.isFinite(n) && n > 0)) throw new Error('Ukuran video tidak valid.')
  const scale = fit ? Math.min(width / sw, height / sh) : Math.max(width / sw, height / sh)
  return { x: (width - sw * scale) / 2, y: (height - sh * scale) / 2, width: sw * scale, height: sh * scale }
}

export function wrapThumbnailText(text: string, maxWidth: number, measure: (text: string) => number): string[] {
  const lines: string[] = []
  for (const paragraph of text.trim().split('\n')) {
    let line = ''
    for (const word of paragraph.trim().split(/\s+/).filter(Boolean)) {
      if (line && measure(`${line} ${word}`) <= maxWidth) { line += ` ${word}`; continue }
      if (line) lines.push(line)
      line = ''
      // Split very long words as well, so titles cannot spill outside the image.
      for (const character of Array.from(word)) {
        if (line && measure(line + character) > maxWidth) { lines.push(line); line = '' }
        line += character
      }
    }
    lines.push(line)
  }
  return lines
}

export function drawThumbnail(canvas: HTMLCanvasElement, frame: HTMLCanvasElement, options: {
  format: ThumbnailFormat; fit: boolean; title: string; style: ThumbnailStyle; position: ThumbnailPosition; textSize: number
  palette?: ThumbnailPalette; font?: ThumbnailFont; uppercase?: boolean
}) {
  const [width, height] = thumbnailSize(options.format)
  canvas.width = width; canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Browser tidak mendukung pembuatan thumbnail.')
  ctx.fillStyle = '#111827'; ctx.fillRect(0, 0, width, height)
  const rect = thumbnailPlacement(frame.width, frame.height, width, height, options.fit)
  ctx.drawImage(frame, rect.x, rect.y, rect.width, rect.height)
  if (!options.title.trim()) return
  const margin = Math.min(width, height) * .065
  const maxWidth = width - margin * 2
  let size = Math.min(width, height) * options.textSize / 100
  const family = options.font === 'display' ? 'Impact, "Arial Black", sans-serif' : 'Arial, sans-serif'
  const text = options.uppercase ? options.title.toLocaleUpperCase('id-ID') : options.title
  let lines: string[] = []
  do {
    ctx.font = `900 ${size}px ${family}`
    lines = wrapThumbnailText(text, maxWidth, text => ctx.measureText(text).width)
    if (lines.length * size * 1.18 <= height * .65) break
    size -= 1
  } while (size > 1)
  const lineHeight = size * 1.18
  const blockHeight = lineHeight * lines.length
  const top = options.position === 'top' ? margin : options.position === 'middle' ? (height - blockHeight) / 2 : height - margin - blockHeight
  if (options.style === 'panel') {
    ctx.fillStyle = 'rgba(0,0,0,.78)'
    ctx.fillRect(margin * .55, top - margin * .3, width - margin * 1.1, blockHeight + margin * .6)
  } else {
    const gradient = ctx.createLinearGradient(0, top - margin, 0, top + blockHeight + margin)
    gradient.addColorStop(0, 'rgba(0,0,0,0)'); gradient.addColorStop(.5, 'rgba(0,0,0,.48)'); gradient.addColorStop(1, 'rgba(0,0,0,0)')
    ctx.fillStyle = gradient; ctx.fillRect(0, top - margin, width, blockHeight + margin * 2)
  }
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.lineJoin = 'round'
  const colors = (thumbnailPalettes.find(p => p.value === options.palette) || thumbnailPalettes[0]!).colors
  lines.forEach((line, index) => {
    const y = top + lineHeight * (index + .5)
    ctx.save()
    ctx.strokeStyle = '#101010'; ctx.lineWidth = Math.max(2, size * .09)
    ctx.fillStyle = options.style === 'yellow' ? '#ffe03b' : '#ffffff'
    if (options.style === 'gradient' || options.style === 'pop') {
      const fill = ctx.createLinearGradient(0, y - size * .45, 0, y + size * .45)
      fill.addColorStop(0, colors[0]); fill.addColorStop(1, colors[1])
      ctx.lineWidth = Math.max(3, size * .14)
      if (options.style === 'pop') {
        // Extrusion is painted behind the letters and included in the JPG.
        ctx.fillStyle = '#101025'; ctx.strokeStyle = '#101025'
        const depth = Math.max(2, Math.round(size * .085))
        for (let offset = depth; offset > 0; offset--) {
          ctx.strokeText(line, width / 2 + offset, y + offset)
          ctx.fillText(line, width / 2 + offset, y + offset)
        }
        ctx.strokeStyle = '#fff9ee'
        ctx.lineWidth = Math.max(2, size * .065)
      }
      ctx.fillStyle = fill
    } else if (options.style === 'neon') {
      ctx.shadowColor = colors[1]; ctx.shadowBlur = size * .3
      ctx.strokeStyle = colors[1]; ctx.lineWidth = Math.max(2, size * .075)
      ctx.strokeText(line, width / 2, y)
      ctx.shadowBlur = size * .12
      ctx.fillStyle = '#ffffff'
    }
    ctx.strokeText(line, width / 2, y); ctx.fillText(line, width / 2, y)
    ctx.restore()
  })
}

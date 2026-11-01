import type { GamingLayout, SourceRect } from '~/types/api'

export type RegionName = 'facecam' | 'gameplay'
export type ResizeCorner = 'nw' | 'ne' | 'sw' | 'se'
export const GAMING_LABEL = 'Gaming (facecam + gameplay)'
export const MIN_REGION = 0.02
const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))
const tidy = (value: number) => Math.round(value * 1e6) / 1e6

export function defaultGaming(): GamingLayout {
  return { facecam: { x: 0, y: 0, width: .25, height: .25 }, gameplay: { x: 0, y: 0, width: 1, height: 1 },
    facecam_height: .28, facecam_fit: 'fill', gameplay_fit: 'fit' }
}

export function validRegion(rect: SourceRect): boolean {
  return !!rect && [rect.x, rect.y, rect.width, rect.height].every(Number.isFinite) &&
    rect.x >= 0 && rect.y >= 0 && rect.width >= MIN_REGION && rect.height >= MIN_REGION &&
    rect.x + rect.width <= 1 + 1e-9 && rect.y + rect.height <= 1 + 1e-9
}

export function validGaming(layout?: GamingLayout): layout is GamingLayout {
  return !!layout && validRegion(layout.facecam) && validRegion(layout.gameplay) &&
    Number.isFinite(layout.facecam_height) && layout.facecam_height >= .15 && layout.facecam_height <= .45 &&
    ['fill', 'fit'].includes(layout.facecam_fit) && ['fill', 'fit'].includes(layout.gameplay_fit)
}

export function editRegion(rect: SourceRect, key: keyof SourceRect, value: number): SourceRect {
  if (!Number.isFinite(value)) return { ...rect }
  const next = { ...rect }
  next[key] = tidy(key === 'x' ? clamp(value, 0, 1 - rect.width) : key === 'y' ? clamp(value, 0, 1 - rect.height)
    : key === 'width' ? clamp(value, MIN_REGION, 1 - rect.x) : clamp(value, MIN_REGION, 1 - rect.y))
  return next
}

export function moveRegion(rect: SourceRect, dx: number, dy: number): SourceRect {
  return { ...rect, x: tidy(clamp(rect.x + dx, 0, 1 - rect.width)), y: tidy(clamp(rect.y + dy, 0, 1 - rect.height)) }
}

export function resizeRegion(rect: SourceRect, corner: ResizeCorner, dx: number, dy: number): SourceRect {
  let left = rect.x; let top = rect.y; let right = rect.x + rect.width; let bottom = rect.y + rect.height
  if (corner.includes('w')) left = clamp(left + dx, 0, right - MIN_REGION)
  else right = clamp(right + dx, left + MIN_REGION, 1)
  if (corner.includes('n')) top = clamp(top + dy, 0, bottom - MIN_REGION)
  else bottom = clamp(bottom + dy, top + MIN_REGION, 1)
  left = tidy(left); top = tidy(top); right = tidy(right); bottom = tidy(bottom)
  return { x: left, y: top, width: tidy(right - left), height: tidy(bottom - top) }
}

export function cornerRegion(corner: ResizeCorner): SourceRect {
  return { x: corner.includes('e') ? .75 : 0, y: corner.includes('s') ? .75 : 0, width: .25, height: .25 }
}

/** Quantize on upright source dimensions, then map to the decoded preview proxy. */
export function pixelRegion(rect: SourceRect, width: number, height: number): SourceRect {
  const left = clamp(Math.floor(rect.x * width), 0, width - 1)
  const top = clamp(Math.floor(rect.y * height), 0, height - 1)
  const right = clamp(Math.ceil((rect.x + rect.width) * width), left + 1, width)
  const bottom = clamp(Math.ceil((rect.y + rect.height) * height), top + 1, height)
  return { x: left, y: top, width: right - left, height: bottom - top }
}

export function gamingTopHeight(outputHeight: number, ratio: number): number {
  return 2 * Math.floor(outputHeight * ratio / 2 + .5)
}

export function panelPlacement(source: SourceRect, panel: SourceRect, fit: 'fill' | 'fit'): SourceRect {
  if (fit === 'fill') return { ...panel }
  const factor = Math.min(panel.width / source.width, panel.height / source.height)
  const width = Math.max(2, 2 * Math.floor(source.width * factor / 2 + 1e-9))
  const height = Math.max(2, 2 * Math.floor(source.height * factor / 2 + 1e-9))
  return { x: panel.x + 2 * Math.floor((panel.width - width) / 4),
    y: panel.y + 2 * Math.floor((panel.height - height) / 4), width, height }
}

/** Crop before scaling: bounded intermediates and the same integer math as FFmpeg. */
export function panelSourceRegion(source: SourceRect, panel: SourceRect, fit: 'fill' | 'fit'): SourceRect {
  if (fit === 'fit') return { ...source }
  let width = source.width; let height = source.height
  if (width * panel.height > height * panel.width) width = clamp(Math.floor(height * panel.width / panel.height + .5), 1, width)
  else height = clamp(Math.floor(width * panel.height / panel.width + .5), 1, height)
  return { x: source.x + Math.floor((source.width - width) / 2), y: source.y + Math.floor((source.height - height) / 2), width, height }
}

export function drawGaming(canvas: HTMLCanvasElement, video: HTMLVideoElement, layout: GamingLayout,
  sourceWidth: number, sourceHeight: number, outputWidth = 1080): boolean {
  if (!validGaming(layout) || !sourceWidth || !sourceHeight || !video.videoWidth || !video.videoHeight || video.readyState < 2) return false
  const height = outputWidth * 16 / 9
  if (canvas.width !== outputWidth || canvas.height !== height) { canvas.width = outputWidth; canvas.height = height }
  const context = canvas.getContext('2d')
  if (!context) return false
  context.fillStyle = '#181b1a'; context.fillRect(0, 0, outputWidth, height)
  const top = gamingTopHeight(height, layout.facecam_height)
  for (const name of ['facecam', 'gameplay'] as const) {
    const source = pixelRegion(layout[name], sourceWidth, sourceHeight)
    const panel = { x: 0, y: name === 'facecam' ? 0 : top, width: outputWidth, height: name === 'facecam' ? top : height - top }
    const fit = layout[`${name}_fit`]
    const cropped = panelSourceRegion(source, panel, fit)
    const destination = panelPlacement(source, panel, fit)
    context.save(); context.beginPath(); context.rect(panel.x, panel.y, panel.width, panel.height); context.clip()
    context.drawImage(video, cropped.x * video.videoWidth / sourceWidth, cropped.y * video.videoHeight / sourceHeight,
      cropped.width * video.videoWidth / sourceWidth, cropped.height * video.videoHeight / sourceHeight,
      destination.x, destination.y, destination.width, destination.height)
    context.restore()
  }
  return true
}

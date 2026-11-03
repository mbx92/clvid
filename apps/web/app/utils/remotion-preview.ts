import type { Cue, SubtitleStyle } from '../types/api'

export interface RemotionPreviewProps {
  cues: Cue[]
  style: SubtitleStyle
  durationMs: number
  width: number
  height: number
  fps: number
  fontUrl: string
}
export interface RemotionController {
  updateProps(props: RemotionPreviewProps): void
  setFrame(frame: number): void
  destroy(): void
}
export interface RemotionVideoStyle { opacity: number; transform: string; transformOrigin: string }
export interface RemotionBridge { mount(element: HTMLElement, props: RemotionPreviewProps): RemotionController; videoStyle(props: RemotionPreviewProps, frame: number): RemotionVideoStyle }
declare global { interface Window { ClipperRemotion?: RemotionBridge } }

/** Use the same 30 fps timeline as export, without rounding across a cue boundary. */
export function remotionFrame(timeMs: number, durationMs: number, fps = 30): number {
  const lastFrame = Math.max(0, Math.ceil(Math.max(0, durationMs) * fps / 1000) - 1)
  return Math.min(lastFrame, Math.max(0, Math.floor((Number.isFinite(timeMs) ? timeMs : 0) * fps / 1000)))
}

let loading: Promise<RemotionBridge> | null = null

/** One shared, lazy bundle for all Vue preview instances. Failures may be retried. */
export function loadRemotionPreview(): Promise<RemotionBridge> {
  if (window.ClipperRemotion) return Promise.resolve(window.ClipperRemotion)
  if (loading) return loading
  loading = new Promise<RemotionBridge>((resolve, reject) => {
    const script = document.createElement('script')
    let settled = false
    const complete = (error?: Error) => {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      script.onload = null
      script.onerror = null
      if (error) { script.remove(); reject(error) }
      else resolve(window.ClipperRemotion!)
    }
    const timeout = setTimeout(() => complete(new Error('Remotion preview timed out')), 15000)
    script.src = '/remotion/player.js'
    script.async = true
    script.onload = () => complete(window.ClipperRemotion ? undefined : new Error('Remotion preview bridge is unavailable'))
    script.onerror = () => complete(new Error('Remotion preview bundle failed to load'))
    document.head.appendChild(script)
  }).catch(error => { loading = null; throw error })
  return loading
}

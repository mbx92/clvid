import type { Ref } from 'vue'

/** Follow displayed video frames, including browsers without requestVideoFrameCallback. */
export function useVideoFrameClock(video: Ref<HTMLVideoElement | null>, onFrame: (milliseconds: number) => void) {
  let frameHandle: number | null = null
  let animationHandle: number | null = null
  let frameVideo: HTMLVideoElement | null = null
  let disposed = false

  const stop = () => {
    if (frameHandle !== null && frameVideo?.cancelVideoFrameCallback) frameVideo.cancelVideoFrameCallback(frameHandle)
    if (animationHandle !== null) cancelAnimationFrame(animationHandle)
    frameHandle = null
    animationHandle = null
    frameVideo = null
  }
  // Do not round a frame before a hard cut up to the cut timestamp.
  const sync = () => { if (video.value && Number.isFinite(video.value.currentTime)) onFrame(Math.floor(video.value.currentTime * 1000 + 0.000001)) }
  const schedule = () => {
    const player = video.value
    if (disposed || !player || player.paused || player.ended || document.hidden) return
    frameVideo = player
    if (typeof player.requestVideoFrameCallback === 'function') {
      frameHandle = player.requestVideoFrameCallback((_now, metadata) => {
        frameHandle = null
        onFrame(Math.floor(metadata.mediaTime * 1000 + 0.000001))
        schedule()
      })
    } else {
      animationHandle = requestAnimationFrame(() => { animationHandle = null; sync(); schedule() })
    }
  }
  const start = () => { stop(); sync(); schedule() }
  const visibility = () => { stop(); if (!document.hidden) start() }
  watch(video, () => { stop(); if (video.value) start() })
  onMounted(() => document.addEventListener('visibilitychange', visibility))
  onBeforeUnmount(() => { disposed = true; stop(); document.removeEventListener('visibilitychange', visibility) })
  return { start, stop, sync }
}

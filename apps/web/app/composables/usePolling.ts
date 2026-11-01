export function usePolling(refresh: () => Promise<unknown>, active: () => boolean) {
  let timer: ReturnType<typeof setTimeout> | undefined
  let stopped = false
  const tick = async () => {
    if (stopped) return
    if (document.visibilityState === 'visible' && active()) {
      try { await refresh() } catch { /* Context owns the visible error. */ }
    }
    if (!stopped) timer = setTimeout(tick, 3000)
  }
  const visible = () => { if (document.visibilityState === 'visible' && active()) void refresh().catch(() => {}) }
  onMounted(() => { timer = setTimeout(tick, 3000); document.addEventListener('visibilitychange', visible) })
  onBeforeUnmount(() => { stopped = true; if (timer) clearTimeout(timer); document.removeEventListener('visibilitychange', visible) })
}

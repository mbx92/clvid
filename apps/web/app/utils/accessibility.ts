export function tabsKeydown(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  const root = event.currentTarget as HTMLElement
  const items = Array.from(root.querySelectorAll<HTMLButtonElement>('[role="tab"]'))
  const current = items.indexOf(event.target as HTMLButtonElement)
  if (current < 0 || !items.length) return
  event.preventDefault()
  const target = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + items.length) % items.length
  items[target]?.focus()
  items[target]?.click()
}

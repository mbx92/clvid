import type { Page } from '~/types/api'
import { computed, ref, shallowRef } from 'vue'

/** Refresh every page already opened so background updates never collapse history. */
export function usePaginatedList<T extends { id: string }>(fetchPage: (page: number, pageSize: number) => Promise<Page<T>>, pageSize = 100) {
  const items = shallowRef<T[]>([])
  const total = ref(0)
  const pagesLoaded = ref(1)
  const loading = ref(false)
  const hasMore = computed(() => pagesLoaded.value * pageSize < total.value)
  let pending: Promise<void> | null = null
  const unique = (values: T[]) => Array.from(new Map(values.map(value => [value.id, value])).values())

  const run = (operation: () => Promise<void>): Promise<void> => {
    if (pending) return pending
    loading.value = true
    pending = operation().finally(() => { loading.value = false; pending = null })
    return pending
  }

  const fetchWindow = async (requestedPages: number) => {
    const first = await fetchPage(1, pageSize)
    const pageCount = Math.min(requestedPages, Math.max(1, Math.ceil(first.total / pageSize)))
    const remaining = await Promise.all(Array.from({ length: pageCount - 1 }, (_, index) => fetchPage(index + 2, pageSize)))
    // Publish only after all requests succeed; failed refreshes retain the visible history.
    items.value = unique([first, ...remaining].flatMap(page => page.items))
    total.value = first.total
    pagesLoaded.value = pageCount
  }

  const refresh = () => run(() => fetchWindow(pagesLoaded.value))

  const loadMore = () => run(async () => {
    if (!hasMore.value) return
    // Refresh the existing window too: new exports may have shifted page boundaries.
    await fetchWindow(pagesLoaded.value + 1)
  })

  return { items, total, loading, hasMore, refresh, loadMore }
}

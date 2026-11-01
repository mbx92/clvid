import tailwindcss from '@tailwindcss/vite'
import { lstat, readlink } from 'node:fs/promises'

// Some Windows network volumes return EISDIR for readlink on regular files.
// Preserve real symlink traversal, while telling Nitro's tracer these are files.
async function traceReadlink(path: string): Promise<string | null> {
  try { return await readlink(path) }
  catch (error: any) {
    // Match NFT's missing-path behavior so extensionless imports can resolve.
    if (['EINVAL', 'ENOENT', 'UNKNOWN'].includes(error.code)) return null
    if (error.code === 'EISDIR' && !(await lstat(path)).isSymbolicLink()) return null
    throw error
  }
}

export default defineNuxtConfig({
  compatibilityDate: '2026-10-30',
  ssr: false,
  devtools: { enabled: false },
  css: ['~/assets/css/main.css', '~/assets/css/workspace.css', '~/assets/css/calendar.css', '~/assets/css/desktop.css', '~/assets/css/select.css'],
  vite: { plugins: [tailwindcss()] },
  nitro: {
    externals: process.platform === 'win32' ? { traceOptions: { readlink: traceReadlink } } : {},
    devProxy: { '/api': { target: 'http://127.0.0.1:8000/api', changeOrigin: false } },
  },
  app: {
    head: {
      title: 'Clipper — Ruang kerja video',
      htmlAttrs: { lang: 'id' },
      meta: [{ name: 'description', content: 'Ruang kerja untuk memilih, mengedit, dan mengekspor klip video.' }],
    },
  },
})

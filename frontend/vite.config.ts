import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { createHash } from 'node:crypto'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const projectId = createHash('sha256').update(path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..').toLowerCase()).digest('hex')

export default defineConfig({
  plugins: [react(), { name: 'genomedebugger-identity', transformIndexHtml() {
    return [{ tag: 'meta', attrs: { name: 'genomedebugger-project', content: projectId }, injectTo: 'head' }]
  } }],
  server: { proxy: { '/api': process.env.GENOMEDEBUGGER_API_URL || 'http://127.0.0.1:8000' } },
  test: { environment: 'jsdom', setupFiles: ['./src/test-setup.ts'], exclude: ['e2e/**', 'node_modules/**'] }
})

import { defineConfig } from '@playwright/test'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const python = path.join(projectRoot, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const database = path.join(os.tmpdir(), `genomedebugger-e2e-${process.pid}.db`)

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  timeout: 30_000,
  use: { baseURL: 'http://127.0.0.1:5174', browserName: 'chromium', trace: 'retain-on-failure' },
  webServer: [
    { command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8001`,
      cwd: path.join(projectRoot, 'backend'),
      env: { ...process.env, GENOMEDEBUGGER_DB: database },
      url: 'http://127.0.0.1:8001/api/health', reuseExistingServer: false, timeout: 30_000 },
    { command: 'npm run dev -- --host 127.0.0.1 --port 5174 --strictPort',
      cwd: path.join(projectRoot, 'frontend'),
      env: { ...process.env, GENOMEDEBUGGER_API_URL: 'http://127.0.0.1:8001' },
      url: 'http://127.0.0.1:5174/', reuseExistingServer: false, timeout: 30_000 },
  ],
})

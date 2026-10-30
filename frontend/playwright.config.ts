import { defineConfig } from '@playwright/test'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {existsSync} from 'node:fs'

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const python = path.join(projectRoot, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const staticDir=path.join(projectRoot,'frontend/dist')
if(!existsSync(path.join(staticDir,'index.html')))throw new Error('Build the interface before browser tests: npm run build')
const browsers = [
  {name:'chromium' as const,apiPort:8001},
  {name:'webkit' as const,apiPort:8002},
  ...(process.env.GENOMEDEBUGGER_TEST_FIREFOX==='1'?[{name:'firefox' as const,apiPort:8003}]:[]),
]

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  timeout: 30_000,
  use: { baseURL: 'http://127.0.0.1:8001', browserName: 'chromium', trace: 'retain-on-failure' },
  projects: browsers.map(({name,apiPort})=>({name,
    ...(name==='chromium'?{}:{testMatch:'**/product-workflows.spec.ts'}),
    use:{browserName:name,baseURL:`http://127.0.0.1:${apiPort}`},
  })),
  webServer: browsers.map(({name,apiPort})=>(
    { command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: path.join(projectRoot, 'backend'),
      env: { ...process.env, GENOMEDEBUGGER_DB:path.join(os.tmpdir(),`genomedebugger-e2e-${process.pid}-${name}.db`), GENOMEDEBUGGER_STATIC_DIR:staticDir, GENOMEDEBUGGER_ALLOWED_ORIGINS: `http://127.0.0.1:${apiPort}` },
      url: `http://127.0.0.1:${apiPort}/api/health`, reuseExistingServer: false, timeout: 30_000 }
  )),
})

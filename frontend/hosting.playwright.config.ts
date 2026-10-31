import {defineConfig} from '@playwright/test'
import os from 'node:os'
import path from 'node:path'
import {fileURLToPath} from 'node:url'

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
const python=path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python')
const baseURL='https://127.0.0.1:8444'
export default defineConfig({
  testDir:'./e2e-hosting',workers:1,timeout:30_000,
  use:{baseURL,ignoreHTTPSErrors:true,browserName:'chromium',trace:'retain-on-failure'},
  webServer:{
    command:`"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8444 --ssl-keyfile "${path.join(root,'.build/hosting-tls/key.pem')}" --ssl-certfile "${path.join(root,'.build/hosting-tls/cert.pem')}"`,
    cwd:path.join(root,'backend'),url:baseURL+'/healthz',ignoreHTTPSErrors:true,reuseExistingServer:false,
    env:{...process.env,GENOMEDEBUGGER_DEPLOYMENT:'public-free',GENOMEDEBUGGER_PUBLIC_ORIGIN:baseURL,
      GENOMEDEBUGGER_SESSION_SECRET:'isolated-browser-test-secret-not-a-production-key',GENOMEDEBUGGER_MAX_DB_MB:'16',
      GENOMEDEBUGGER_WORKSPACES_DIR:path.join(os.tmpdir(),`genomedebugger-public-e2e-${process.pid}`),
      GENOMEDEBUGGER_STATIC_DIR:path.join(root,'frontend/dist')},
  },
})

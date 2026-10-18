param([switch]$NoBrowser, [switch]$Restart)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$vitePath = Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'
$dataPath = Join-Path $projectRoot 'data'

if (-not (Test-Path -LiteralPath $pythonPath) -or -not (Test-Path -LiteralPath $vitePath)) {
    throw 'Install backend requirements and run npm ci in frontend before starting the site.'
}
New-Item -ItemType Directory -Path $dataPath -Force | Out-Null

if ($Restart) {
    $listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if ($processInfo.CommandLine -notmatch 'uvicorn app\.main:app --host 127\.0\.0\.1 --port 8000') {
            throw 'Port 8000 belongs to another application; refusing to restart it.'
        }
        Stop-Process -Id $listener.OwningProcess -Force
    }
}

function Test-LocalUrl([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

if (-not (Test-LocalUrl 'http://127.0.0.1:8000/api/health')) {
    Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') `
        -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $dataPath 'backend-stdout.log') `
        -RedirectStandardError (Join-Path $dataPath 'backend-stderr.log') | Out-Null
}
if (-not (Test-LocalUrl 'http://127.0.0.1:5173/')) {
    $nodePath = (Get-Command node -ErrorAction Stop).Source
    Start-Process -FilePath $nodePath -ArgumentList @($vitePath,'--host','127.0.0.1','--port','5173','--strictPort') `
        -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $dataPath 'frontend-stdout.log') `
        -RedirectStandardError (Join-Path $dataPath 'frontend-stderr.log') | Out-Null
}

for ($attempt = 0; $attempt -lt 20; $attempt++) {
    if ((Test-LocalUrl 'http://127.0.0.1:8000/api/health') -and (Test-LocalUrl 'http://127.0.0.1:5173/')) {
        Write-Output 'GenomeDebugger is ready at http://127.0.0.1:5173/'
        if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:5173/' }
        exit 0
    }
    Start-Sleep -Milliseconds 500
}
throw 'GenomeDebugger did not become ready. Inspect data/backend-stderr.log and data/frontend-stderr.log.'

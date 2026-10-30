param([switch]$NoBrowser, [switch]$Restart, [switch]$Stop)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$backendPath = Join-Path $projectRoot 'backend'
$vitePath = Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'
$dataPath = Join-Path $projectRoot 'data'
$sha = [System.Security.Cryptography.SHA256]::Create()
try {
    $projectId = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($projectRoot.ToLowerInvariant())))).Replace('-', '').ToLowerInvariant()
} finally { $sha.Dispose() }

if (-not $Stop -and (-not (Test-Path -LiteralPath $pythonPath) -or -not (Test-Path -LiteralPath $vitePath))) {
    throw 'Install backend requirements and run npm ci in frontend before starting the site.'
}
New-Item -ItemType Directory -Path $dataPath -Force | Out-Null

function Get-LocalListener([int]$Port) {
    return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}
function Test-OwnedProcess($ProcessInfo, [int]$Port) {
    $command = [string]$ProcessInfo.CommandLine
    if ($Port -eq 5173) {
        return $command -match ('(?:^|\s)"?' + [regex]::Escape($vitePath) + '"?(?:\s|$)')
    }
    if ($command -notmatch '(?:^|\s)-m\s+uvicorn\s+app\.main:app(?:\s|$)') { return $false }
    # An explicit module directory proves which checkout is being served.
    if ($command -match ('--app-dir\s+"?' + [regex]::Escape($backendPath) + '"?(?:\s|$)')) { return $true }
    # A project venv alone does not prove the working directory. Older launch
    # commands must also identify this checkout through their health response.
    $launcherOwned = $command -match ('(?:^|\s)"?' + [regex]::Escape($pythonPath) + '"?(?:\s|$)')
    if ($ProcessInfo.ParentProcessId) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($ProcessInfo.ParentProcessId)"
        $launcherOwned = $launcherOwned -or ($parent.ExecutablePath -eq $pythonPath -and $parent.CommandLine -match 'uvicorn\s+app\.main:app(?:\s|$)')
    }
    return ($launcherOwned -and (Test-LocalUrl 'http://127.0.0.1:8000/api/health'))
}
function Assert-OwnedListeners([int]$Port) {
    $listeners = Get-LocalListener $Port
    foreach ($listener in $listeners) {
        $info = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if (-not (Test-OwnedProcess $info $Port)) {
            throw "Port $Port belongs to another application or its ownership cannot be verified. Free the port before starting GenomeDebugger."
        }
    }
    return $listeners
}
function Test-LocalUrl([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -ne 200) { return $false }
        if ($Url.EndsWith('/api/health')) {
            $body = $response.Content | ConvertFrom-Json
            return ($body.application -eq 'GenomeDebugger' -and $body.project_id -eq $projectId -and $body.status -eq 'ok')
        }
        return $response.Content -match ('<meta\s+name="genomedebugger-project"\s+content="' + $projectId + '"')
    } catch {
        return $false
    }
}

# Validate both ports before stopping or launching anything.
$backendListeners = @(Assert-OwnedListeners 8000)
$frontendListeners = @(Assert-OwnedListeners 5173)
if ($Stop) {
    foreach ($listener in @($backendListeners + $frontendListeners) | Sort-Object -Property OwningProcess -Unique) {
        Stop-Process -Id $listener.OwningProcess -Force
    }
    Write-Output 'GenomeDebugger local services stopped.'
    exit 0
}
if ($Restart) {
    foreach ($listener in @($backendListeners + $frontendListeners) | Sort-Object -Property OwningProcess -Unique) {
        Stop-Process -Id $listener.OwningProcess -Force
    }
}

if (-not (Test-LocalUrl 'http://127.0.0.1:8000/api/health')) {
    if (@(Get-LocalListener 8000).Count) { throw 'GenomeDebugger on port 8000 is not ready or uses an older version. Try -Restart and inspect data/backend-stderr.log.' }
    Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','app.main:app','--app-dir',('"' + $backendPath + '"'),'--host','127.0.0.1','--port','8000') `
        -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $dataPath 'backend-stdout.log') `
        -RedirectStandardError (Join-Path $dataPath 'backend-stderr.log') | Out-Null
}
if (-not (Test-LocalUrl 'http://127.0.0.1:5173/')) {
    if (@(Get-LocalListener 5173).Count) { throw 'GenomeDebugger frontend is not ready. Inspect data/frontend-stderr.log and restart its Vite process if needed.' }
    $nodePath = (Get-Command node -ErrorAction Stop).Source
    Start-Process -FilePath $nodePath -ArgumentList @(('"' + $vitePath + '"'),'--host','127.0.0.1','--port','5173','--strictPort') `
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

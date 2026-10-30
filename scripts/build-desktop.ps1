$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$releaseName = 'windows-0.8.3-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$outputPath = Join-Path $projectRoot ('release\' + $releaseName)
$buildPath = Join-Path $projectRoot ('.build\' + $releaseName)
if (Test-Path -LiteralPath $outputPath) { throw 'Release directory already exists. Choose a new build directory.' }
& $pythonPath -m pip install 'pyinstaller==6.22.3'
if ($LASTEXITCODE -ne 0) { throw 'Packaging dependency installation failed.' }
Push-Location (Join-Path $projectRoot 'frontend')
try { & npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' } } finally { Pop-Location }
New-Item -ItemType Directory -Path $buildPath -Force | Out-Null
& $pythonPath -m PyInstaller --name GenomeDebugger --onedir --windowed --noupx --paths (Join-Path $projectRoot 'backend') --hidden-import app.main --collect-submodules uvicorn --collect-submodules app --exclude-module pytest --exclude-module IPython --distpath $outputPath --workpath (Join-Path $buildPath 'work') --specpath $buildPath (Join-Path $PSScriptRoot 'desktop.py')
if ($LASTEXITCODE -ne 0) { throw 'Desktop packaging failed.' }
$applicationPath = Join-Path $outputPath 'GenomeDebugger'
New-Item -ItemType Directory -Path (Join-Path $applicationPath 'frontend') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot 'frontend\dist') -Destination (Join-Path $applicationPath 'frontend') -Recurse
Copy-Item -LiteralPath (Join-Path $projectRoot 'fixtures') -Destination $applicationPath -Recurse
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\desktop-guide.md') -Destination (Join-Path $applicationPath 'README.md')
$archivePath = Join-Path $outputPath 'GenomeDebugger-0.8.3-Windows.zip'
Compress-Archive -LiteralPath $applicationPath -DestinationPath $archivePath
(Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant() | Set-Content -LiteralPath ($archivePath + '.sha256')
Write-Output ('Portable desktop build: ' + $archivePath)

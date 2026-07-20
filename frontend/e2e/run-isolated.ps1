param([switch]$Headed)

$ErrorActionPreference = "Stop"
$frontend = Split-Path -Parent $PSScriptRoot
$root = Split-Path -Parent $frontend
$docker = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
$container = "studypilot-round17-e2e-$PID"
$appPath = (Resolve-Path (Join-Path $root "backend\app")).Path
$exitCode = 1

try {
  & $docker compose -f (Join-Path $root "docker-compose.yml") run --rm --no-deps -d `
    --name $container -p "127.0.0.1:18000:8000" `
    -e "DATABASE_URL=sqlite:////tmp/studypilot-round17.db" `
    -e "UPLOAD_DIR=/tmp/studypilot-round17-uploads" `
    -e "AUTO_CREATE_TABLES=true" `
    -e "SYNC_DOCUMENT_PROCESSING=true" `
    -e "LLM_PROVIDER=mock" `
    -v "${appPath}:/app/backend/app:ro" `
    backend
  if ($LASTEXITCODE -ne 0) { throw "Unable to start isolated backend container" }

  $ready = $false
  for ($attempt = 0; $attempt -lt 60; $attempt += 1) {
    try {
      $health = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:18000/health" -TimeoutSec 2
      if ($health.StatusCode -eq 200) { $ready = $true; break }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }
  if (-not $ready) { throw "Isolated backend did not become healthy" }

  $env:E2E_API_ORIGIN = "http://127.0.0.1:18000"
  $env:VITE_API_PROXY_TARGET = "http://127.0.0.1:18000"
  $env:VITE_ENABLE_MOCK = "false"
  Push-Location $frontend
  try {
    $playwright = Join-Path $frontend "node_modules\.bin\playwright.cmd"
    if ($Headed) {
      & $playwright test --headed
    } else {
      & $playwright test
    }
    $exitCode = $LASTEXITCODE
  } finally {
    Pop-Location
  }
} finally {
  & $docker rm -f $container 2>$null | Out-Null
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
    (Join-Path $frontend "test-results"), (Join-Path $frontend "playwright-report")
}

exit $exitCode

param(
  [switch]$Headed,
  [string]$DockerExecutable = "",
  [string[]]$Spec = @(),
  [string]$Grep = "",
  [int]$TestTimeout = 0,
  [switch]$KeepArtifacts,
  [ValidateSet("", "desktop-chrome", "mobile-chrome")]
  [string]$Project = ""
)

$ErrorActionPreference = "Stop"
$frontend = Split-Path -Parent $PSScriptRoot
$root = Split-Path -Parent $frontend
$container = "studypilot-round17-e2e-$PID"
$appPath = (Resolve-Path (Join-Path $root "backend\app")).Path
$e2ePath = (Resolve-Path $PSScriptRoot).Path
$exitCode = 1

function Resolve-DockerExecutable {
  if ($DockerExecutable) {
    if (Test-Path -LiteralPath $DockerExecutable) { return (Resolve-Path -LiteralPath $DockerExecutable).Path }
    throw "Docker executable from -DockerExecutable was not found: $DockerExecutable"
  }
  if ($env:DOCKER_EXE) {
    if (Test-Path -LiteralPath $env:DOCKER_EXE) { return (Resolve-Path -LiteralPath $env:DOCKER_EXE).Path }
    throw "Docker executable from DOCKER_EXE was not found: $env:DOCKER_EXE"
  }
  $command = Get-Command docker -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }
  $default = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
  if (Test-Path -LiteralPath $default) { return $default }
  throw "Docker CLI was not found. Use -DockerExecutable, set DOCKER_EXE, add docker to PATH, or install Docker Desktop."
}

$docker = Resolve-DockerExecutable

try {
  & $docker compose -f (Join-Path $root "docker-compose.yml") run --rm --no-deps -d `
    --name $container -p "127.0.0.1:18000:8000" `
    -e "DATABASE_URL=sqlite:////tmp/studypilot-round17.db" `
    -e "UPLOAD_DIR=/tmp/studypilot-round17-uploads" `
    -e "AUTO_CREATE_TABLES=true" `
    -e "SYNC_DOCUMENT_PROCESSING=true" `
    -e "LLM_PROVIDER=mock" `
    -v "${appPath}:/app/backend/app:ro" `
    -v "${e2ePath}:/app/e2e:ro" `
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
  $env:E2E_CONTAINER_NAME = $container
  $env:E2E_DOCKER_EXE = $docker
  $env:VITE_API_PROXY_TARGET = "http://127.0.0.1:18000"
  $env:VITE_ENABLE_MOCK = "false"
  Push-Location $frontend
  try {
    $playwright = Join-Path $frontend "node_modules\.bin\playwright.cmd"
    $arguments = @("test")
    if ($Spec.Count) { $arguments += $Spec }
    if ($Grep) { $arguments += @("--grep", $Grep) }
    if ($TestTimeout -gt 0) { $arguments += "--timeout=$TestTimeout" }
    if ($Project) { $arguments += "--project=$Project" }
    if ($Headed) { $arguments += "--headed" }
    & $playwright @arguments
    $exitCode = $LASTEXITCODE
  } finally {
    Pop-Location
  }
} finally {
  & $docker rm -f $container 2>$null | Out-Null
  if (-not $KeepArtifacts) {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
      (Join-Path $frontend "test-results"), (Join-Path $frontend "playwright-report")
  }
}

exit $exitCode

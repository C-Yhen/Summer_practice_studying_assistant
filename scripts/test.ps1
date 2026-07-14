$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Push-Location backend
try {
    python -m pytest ..\tests\backend -q
}
finally {
    Pop-Location
}

python -m pytest tests\mcp -q

Push-Location frontend
try {
    npm run build
}
finally {
    Pop-Location
}


$ErrorActionPreference = "Stop"
$base = if ($env:API_BASE_URL) { $env:API_BASE_URL.TrimEnd("/") } else { "http://localhost:8000" }

$health = Invoke-RestMethod -Method Get -Uri "$base/health"
if (-not $health) {
    throw "健康检查未返回内容"
}

Write-Host "后端健康检查通过: $($health | ConvertTo-Json -Compress)"


param(
    [ValidateSet("auto", "hourly", "morning", "evening")]
    [string]$Mode = "hourly",
    [switch]$DryRun,
    [switch]$NoCrawl,
    [double]$Hours = 0
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$python = Join-Path $root "vendor\TrendRadar\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "未找到虚拟环境：$python。请先运行：uv sync --frozen --no-dev（在 vendor\TrendRadar 下）"
    exit 1
}

$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)$') {
            Set-Item -Path ("env:" + $matches[1]) -Value $matches[2].Trim()
        }
    }
}

$env:PYTHONIOENCODING = "utf-8"
$arguments = @("-m", "intel.run", "--mode", $Mode)
if ($DryRun) { $arguments += "--dry-run" }
if ($NoCrawl) { $arguments += "--no-crawl" }
if ($Hours -gt 0) { $arguments += @("--hours", "$Hours") }

& $python @arguments
exit $LASTEXITCODE
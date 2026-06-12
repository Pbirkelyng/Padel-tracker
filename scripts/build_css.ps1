# Build Tailwind CSS for production (Windows).
# Requires Node.js/npx or the Tailwind standalone CLI on PATH.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Input = "app/static/src/input.css"
$Output = "app/static/app.css"

if (Get-Command npx -ErrorAction SilentlyContinue) {
    npx --yes tailwindcss@3.4.17 -i $Input -o $Output --minify
    Write-Host "Built $Output via npx"
    exit 0
}

$Standalone = Join-Path $Root "bin/tailwindcss.exe"
if (Test-Path $Standalone) {
    & $Standalone -i $Input -o $Output --minify
    Write-Host "Built $Output via standalone CLI"
    exit 0
}

Write-Error "Install Node.js (npx) or download tailwindcss standalone to bin/tailwindcss.exe"
exit 1

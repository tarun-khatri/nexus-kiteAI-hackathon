# PowerShell script to start all NEXUS external marketplace agents
# Each agent registers itself with the NEXUS backend on startup.
# Make sure the backend is running at http://localhost:8000 first.

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$nexusUrl = if ($env:NEXUS_URL) { $env:NEXUS_URL } else { "http://localhost:8000" }

Write-Host "Starting NEXUS external marketplace agents..." -ForegroundColor Cyan
Write-Host "Backend expected at: $nexusUrl"
Write-Host ""

$agents = @(
    @{ Name = "defi-agent";        Port = 5001 },
    @{ Name = "dexscreener-agent"; Port = 5002 },
    @{ Name = "security-agent";    Port = 5003 }
)

foreach ($agent in $agents) {
    $path = Join-Path $scriptDir $agent.Name
    $reqs = Join-Path $path "requirements.txt"
    if (Test-Path $reqs) {
        Write-Host "Installing deps for $($agent.Name)..."
        pip install -q -r $reqs
    }
}

Write-Host ""
Write-Host "Launching agents..."

$processes = @()
foreach ($agent in $agents) {
    $path = Join-Path $scriptDir $agent.Name
    $env:AGENT_PORT = $agent.Port
    $p = Start-Process -FilePath "uvicorn" `
        -ArgumentList "app:app", "--host", "0.0.0.0", "--port", $agent.Port `
        -WorkingDirectory $path `
        -PassThru `
        -NoNewWindow
    $processes += $p
    Write-Host "  $($agent.Name) (PID $($p.Id)) -> http://localhost:$($agent.Port)"
}

Write-Host ""
Write-Host "Press Ctrl+C to stop all agents"

try {
    Wait-Process -Id ($processes | ForEach-Object { $_.Id })
} finally {
    foreach ($p in $processes) {
        if (-not $p.HasExited) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

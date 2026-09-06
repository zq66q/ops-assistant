# ============================================================
#  ops-assistant one-click launcher (backend 8600 + frontend 8601)
#  - cleans leftover 8600/8601 processes before start
#  - waits until backend+frontend are healthy, THEN opens browser
#  - closing this window or Ctrl+C stops all services
# ============================================================
$ErrorActionPreference = 'SilentlyContinue'
Set-Location 'D:\ops-assistant'

function Stop-OpsPorts {
    $pids = @()
    netstat -ano | ForEach-Object {
        if ($_ -match ':8600\s' -or $_ -match ':8601\s') {
            $t = $_ -split '\s+'
            $p = $t[-1]
            if ($p -match '^\d+$') { $pids += $p }
        }
    }
    foreach ($p in ($pids | Select-Object -Unique)) {
        if ($p -match '^\d+$') { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }
    }
}

Write-Host '== [1/4] clean leftover ops-assistant processes (8600/8601) ==' -ForegroundColor Cyan
Stop-OpsPorts
Start-Sleep -Seconds 1

Write-Host '== [2/4] start backend (8600) ==' -ForegroundColor Green
Start-Process 'D:\ops-assistant\.venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8600' -WorkingDirectory 'D:\ops-assistant' -NoNewWindow

Write-Host '== [3/4] start Streamlit frontend (8601) ==' -ForegroundColor Green
Start-Process 'D:\ops-assistant\.venv\Scripts\streamlit.exe' -ArgumentList 'run','web/app.py','--server.headless','true','--server.port','8601','--server.address','0.0.0.0' -WorkingDirectory 'D:\ops-assistant' -NoNewWindow

Write-Host '== waiting for services to be ready ==' -ForegroundColor DarkGray
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $h = (Invoke-WebRequest 'http://127.0.0.1:8600/health' -UseBasicParsing -TimeoutSec 2).StatusCode
        $u = (Invoke-WebRequest 'http://127.0.0.1:8601' -UseBasicParsing -TimeoutSec 2).StatusCode
        if ($h -eq 200 -and $u -eq 200) { $ok = $true; break }
    } catch { }
}

if (-not $ok) {
    Write-Host ''
    Write-Host '[FAILED] backend/frontend did not become ready. See log above. Exiting.' -ForegroundColor Red
    Stop-OpsPorts
    Start-Sleep -Seconds 3
    exit 1
}

Write-Host '== [4/4] services ready, opening browser ==' -ForegroundColor Green
Start-Process 'http://127.0.0.1:8601'

Write-Host ''
Write-Host 'backend + frontend running. Browser opened at http://127.0.0.1:8601' -ForegroundColor Yellow
Write-Host 'When done: close this window (or press Ctrl+C) to stop all services.' -ForegroundColor Yellow
Write-Host 'Note: Streamlit is a resident server; closing only the browser tab does NOT stop it.' -ForegroundColor DarkGray
Write-Host ''

# Keep this window open. Closing it terminates the attached backend/frontend processes.
while ($true) { Start-Sleep -Seconds 5 }

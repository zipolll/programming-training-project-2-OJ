[CmdletBinding()]
param([switch]$NoReload)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$backendProcess = $null
$frontendProcess = $null
$frontendLog = Join-Path $projectRoot "data\runtime\start-dev\frontend.log"
$frontendErrorLog = Join-Path $projectRoot "data\runtime\start-dev\frontend-error.log"

function Assert-PortAvailable {
    param([int]$Port, [string]$Service)

    $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    if ($listeners | Where-Object { $_.Port -eq $Port }) {
        throw "$Service port $Port is already in use. Stop the existing service before running start_dev.ps1; no new services were started."
    }
}

function Get-FrontendFailure {
    param([System.Diagnostics.Process]$Process, [string]$OutputLog, [string]$ErrorLog)

    $Process.Refresh()
    $code = $Process.ExitCode
    if ($null -eq $code) { $code = "unavailable" }
    $details = @(
        foreach ($log in @($OutputLog, $ErrorLog)) {
            if (Test-Path -LiteralPath $log) {
                Get-Content -LiteralPath $log -Tail 20
            }
        }
    ) -join [Environment]::NewLine
    return "Frontend exited (exit code $code). Logs: $OutputLog ; $ErrorLog`n$details"
}

function Stop-ProcessTree {
    param([System.Diagnostics.Process]$Process)

    if ($null -eq $Process) {
        return
    }

    try {
        if (-not $Process.HasExited) {
            & taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null
        }
    }
    catch {
        # The process may already have exited between the check and taskkill.
    }
}

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    Write-Error "Virtual environment not found: $pythonPath"
    Write-Host "Create .venv and install requirements before running this script."
    exit 1
}

Push-Location $projectRoot
try {
    # An old service must not satisfy the health check for a newly spawned process.
    Assert-PortAvailable -Port 8000 -Service "Backend"
    Assert-PortAvailable -Port 8501 -Service "Frontend"

    Write-Host "Checking Python environment..."
    & $pythonPath -c "import fastapi, streamlit, uvicorn" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Required packages are missing. Install them with:"
        Write-Host "  uv pip install --link-mode=copy --python .\.venv\Scripts\python.exe -r requirements-dev.txt"
        exit 1
    }

    $env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = "false"

    $backendArguments = @("-m", "uvicorn", "backend.app.main:app")
    if (-not $NoReload) {
        $backendArguments += "--reload"
    }
    $mode = if ($NoReload) { "acceptance" } else { "development" }
    Write-Host "Starting backend at http://localhost:8000 ($mode mode) ..."
    $backendProcess = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList $backendArguments `
        -WorkingDirectory $projectRoot `
        -NoNewWindow `
        -PassThru

    $backendReady = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($backendProcess.HasExited) {
            throw "Backend exited during startup (exit code $($backendProcess.ExitCode))."
        }

        try {
            $response = Invoke-WebRequest `
                -Uri "http://127.0.0.1:8000/api/health" `
                -UseBasicParsing `
                -TimeoutSec 1
            if ($response.StatusCode -eq 200) {
                $backendReady = $true
                break
            }
        }
        catch {
            # The backend may still be importing modules or initializing SQLite.
        }
    }

    if (-not $backendReady) {
        throw "Backend did not become ready at http://localhost:8000/api/health."
    }

    $frontendArguments = @(
        "-m", "streamlit", "run", "frontend/app.py",
        "--server.address", "127.0.0.1", "--server.port", "8501",
        "--server.headless", "true"
    )
    if ($NoReload) {
        $frontendArguments += @("--server.fileWatcherType", "none")
    }
    else {
        $frontendArguments += @("--server.fileWatcherType", "poll")
    }
    New-Item -ItemType Directory -Path (Split-Path $frontendLog) -Force | Out-Null
    Write-Host "Starting frontend at http://localhost:8501 ..."
    $frontendProcess = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList $frontendArguments `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $frontendLog `
        -RedirectStandardError $frontendErrorLog `
        -PassThru
    # Keep a process handle open so Windows PowerShell can retrieve its exit code.
    $null = $frontendProcess.Handle
    Write-Host "Frontend logs: $frontendLog ; $frontendErrorLog"

    $frontendReady = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($frontendProcess.HasExited) {
            throw (Get-FrontendFailure $frontendProcess $frontendLog $frontendErrorLog)
        }
        try {
            $response = Invoke-WebRequest `
                -Uri "http://127.0.0.1:8501/_stcore/health" `
                -UseBasicParsing `
                -TimeoutSec 1
            if ($response.StatusCode -eq 200) {
                $frontendReady = $true
                break
            }
        }
        catch {
            # Streamlit may still be importing the application and building its first session.
        }
    }
    if (-not $frontendReady) {
        throw "Frontend did not become ready at http://localhost:8501."
    }

    Start-Process "http://localhost:8501"

    Write-Host ""
    Write-Host "OJ is running: http://localhost:8501"
    Write-Host "Press Ctrl+C to stop both frontend and backend."

    while (-not $backendProcess.HasExited -and -not $frontendProcess.HasExited) {
        Start-Sleep -Seconds 1
    }

    if ($backendProcess.HasExited) {
        throw "Backend stopped unexpectedly (exit code $($backendProcess.ExitCode))."
    }
    if ($frontendProcess.HasExited) {
        throw (Get-FrontendFailure $frontendProcess $frontendLog $frontendErrorLog)
    }
}
finally {
    Write-Host "Stopping OJ services..."
    Stop-ProcessTree -Process $frontendProcess
    Stop-ProcessTree -Process $backendProcess
    Pop-Location
}

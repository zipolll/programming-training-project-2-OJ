[CmdletBinding()]
param([switch]$NoReload)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$backendProcess = $null
$frontendProcess = $null

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
    Write-Host "Starting frontend at http://localhost:8501 ..."
    $frontendProcess = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList $frontendArguments `
        -WorkingDirectory $projectRoot `
        -NoNewWindow `
        -PassThru

    $frontendReady = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($frontendProcess.HasExited) {
            throw "Frontend exited during startup (exit code $($frontendProcess.ExitCode))."
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
        throw "Frontend stopped unexpectedly (exit code $($frontendProcess.ExitCode))."
    }
}
finally {
    Write-Host "Stopping OJ services..."
    Stop-ProcessTree -Process $frontendProcess
    Stop-ProcessTree -Process $backendProcess
    Pop-Location
}

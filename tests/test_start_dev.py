"""Windows launcher checks using isolated ports/processes, without OJ services."""

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell launcher")
ROOT = Path(__file__).resolve().parents[1]
LOAD_FUNCTIONS = r"""
$ErrorActionPreference = 'Stop'
$parseErrors = $null
$tokens = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path (Get-Location) 'scripts/start_dev.ps1'), [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
$ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst]
}, $false) |
    ForEach-Object { . ([scriptblock]::Create($_.Extent.Text)) }
"""


def run_powershell(script: str, **environment: str) -> None:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", LOAD_FUNCTIONS + script],
        cwd=ROOT,
        env={**os.environ, **environment},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_port_guard_rejects_listener_and_accepts_released_port() -> None:
    run_powershell(r"""
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$listener.Start()
$port = $listener.LocalEndpoint.Port
try {
    $failure = ''
    try { Assert-PortAvailable -Port $port -Service 'Frontend' }
    catch { $failure = $_.Exception.Message }
    if ($failure -notlike "*Frontend port $port is already in use*") {
        throw 'Missing actionable port error'
    }
} finally { $listener.Stop() }
Assert-PortAvailable -Port $port -Service 'Frontend'
""")


def test_frontend_failure_preserves_exit_code_and_log(tmp_path: Path) -> None:
    run_powershell(
        r"""
$outLog = Join-Path $env:OJ_TEST_LOG_DIR 'stdout.log'
$errLog = Join-Path $env:OJ_TEST_LOG_DIR 'stderr.log'
$childCode = "[Console]::Error.WriteLine('Port 8501 is not available'); exit 7"
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($childCode))
$child = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') `
    -ArgumentList '-NoProfile','-NonInteractive','-EncodedCommand',$encoded `
    -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
$null = $child.Handle
if (-not $child.WaitForExit(10000)) { $child.Kill(); throw 'Child did not finish' }
$message = Get-FrontendFailure $child $outLog $errLog
if ($message -notlike '*exit code 7*' -or $message -notlike '*Port 8501 is not available*') {
    throw "Lost exit diagnostics: $message"
}
""",
        OJ_TEST_LOG_DIR=str(tmp_path),
    )

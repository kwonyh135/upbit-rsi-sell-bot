$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimePython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$python = Get-Command python -ErrorAction SilentlyContinue

if ($python) {
    $pythonPath = $python.Source
}
elseif (Test-Path -LiteralPath $runtimePython) {
    $pythonPath = $runtimePython
}
else {
    throw "Python executable was not found."
}

Set-Location -LiteralPath $projectRoot
& $pythonPath -m streamlit run huntbot/dashboard_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false

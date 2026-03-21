param(
    [string]$Season = "s1",
    [string]$Start = "",
    [string]$End = "",
    [int]$Minutes = 30,
    [int]$PrintOrders = 20,
    [string]$Timezone = "Asia/Shanghai",
    [switch]$Debug
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SystemPython = "python"
$BacktestScript = Join-Path $ProjectRoot "src\trader_incubator\backtest.py"

if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonExe = $SystemPython
}

$env:PYTHONPATH = (Join-Path $ProjectRoot "src")

$ArgsList = @(
    $BacktestScript,
    "--season", $Season,
    "--timezone", $Timezone,
    "--minutes", "$Minutes",
    "--print-orders", "$PrintOrders"
)

if ($Start -ne "") {
    $ArgsList += @("--start", $Start)
}
if ($End -ne "") {
    $ArgsList += @("--end", $End)
}
if ($Debug) {
    $ArgsList += "--debug"
}

& $PythonExe @ArgsList

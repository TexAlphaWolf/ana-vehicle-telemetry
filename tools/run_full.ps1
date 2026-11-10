# The full measurement on your own computer, in Docker (no network, read-only root, no capabilities), from Windows
# PowerShell: how fast the analysis is for growing log sizes, how accurate it is against the truth of synthetic logs, and that
# it agrees with the literal implementation.
# Usage: .\tools\run_full.ps1 [-Sizes 10000,100000,1000000,3000000] [-Repeat 5] [-Draws 50] [-Seeds 20] [-Out results]
param(
    [string]$Sizes = "10000,100000,1000000,3000000",
    [int]$Repeat = 5,
    [int]$Draws = 50,
    [int]$Seeds = 20,
    [string]$Out = "results"
)
# Windows PowerShell 5.1 turns anything a program writes on stderr into an error under "Stop": docker and vtel print
# their progress there, so only the exit code is looked at.
$ErrorActionPreference = "Continue"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$outFull = (Resolve-Path -LiteralPath $Out).Path

docker build -t vtel .
if ($LASTEXITCODE -ne 0) { Write-Host "docker build failed"; exit 1 }

Write-Host "== bench (sizes $Sizes, $Repeat runs each, $Draws random logs checked, $Seeds seeds for the accuracy) =="
docker run --rm --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --network none -v "${outFull}:/out" vtel bench --sizes $Sizes --repeat $Repeat --draws $Draws --seeds $Seeds --out /out
if ($LASTEXITCODE -ne 0) { Write-Host "bench failed (exit code $LASTEXITCODE)"; exit 1 }
Write-Host "Done. Send me $Out\bench.json, $Out\bench.md and $Out\summary.png."

# End to end inside the image, from Windows PowerShell: a synthetic log and its truth are written to a volume, validated,
# analysed and scored, the report is rebuilt from its JSON, the two implementations are compared and the benchmark runs small
# (read-only root, no capabilities, no network). Needs Docker Desktop.
# Usage: .\tools\docker_e2e.ps1 [-Image vtel]
param([string]$Image = "vtel")
$ErrorActionPreference = "Stop"

$id = Get-Random
$vol = "vtel-e2e-$id"
$secure = @("--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--network", "none", "-v", "${vol}:/data")

# Windows PowerShell 5.1 turns a program's message on stderr into an error under "Stop": the commands that are expected to
# fail run with errors not terminating, and only their exit code is looked at.
function Invoke-VtelCode([int[]]$Allowed, [string[]]$VtelArgs) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = docker run --rm @secure $Image @VtelArgs 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    if ($Allowed -notcontains $code) { throw "vtel $VtelArgs exited with $code : $out" }
    ($out | Out-String)
}
function Invoke-Vtel([string[]]$VtelArgs) { Invoke-VtelCode @(0) $VtelArgs }
function Read-Volume($path) {
    $out = docker run --rm --entrypoint cat -v "${vol}:/data" $Image $path 2>$null
    if ($LASTEXITCODE -ne 0) { throw "cannot read $path" }
    ($out | Out-String)
}
function Assert-Contains($text, $needle) { if ($text -notmatch [regex]::Escape($needle)) { throw "expected '$needle' in: $text" } }

try {
    docker volume create $vol | Out-Null
    docker run --rm --user 0 -v "${vol}:/data" --entrypoint chown $Image 10001 /data
    if ($LASTEXITCODE -ne 0) { throw "could not prepare the volume" }

    Assert-Contains (Invoke-Vtel @("generate", "-o", "/data/drive.csv", "--truth", "/data/truth.json", "--days", "3", "--seed", "4")) "written: /data/drive.csv"
    Assert-Contains (Invoke-Vtel @("validate", "/data/drive.csv")) "channels: speed, rpm, throttle, load, coolant, fuel"

    $run = Invoke-Vtel @("analyze", "/data/drive.csv", "--truth", "/data/truth.json", "--out", "/data/out")
    Assert-Contains $run "/data/drive.csv: "
    Assert-Contains $run "trips matched"
    Assert-Contains $run ", 0 false alarms"
    $md = Read-Volume "/data/out/report.md"
    Invoke-Vtel @("render", "/data/out/report.json", "-o", "/data/out/again.md") | Out-Null
    if ((Read-Volume "/data/out/again.md") -ne $md) { throw "the report rebuilt from the JSON is not identical" }

    Assert-Contains (Invoke-Vtel @("analyze")) "demo drive log (synthetic, 14 days, seed 1): 52,542 samples, 27 trips"
    Assert-Contains (Invoke-Vtel @("verify", "--draws", "5")) "6 of 6 comparisons agree with the literal implementation"

    Invoke-Vtel @("bench", "--sizes", "2000,5000", "--repeat", "1", "--draws", "3", "--ref-samples", "2000", "--seeds", "3", "--out", "/data/bench") | Out-Null
    Assert-Contains (Read-Volume "/data/bench/bench.json") '"ok": true'

    Invoke-VtelCode @(2) @("validate", "/data/nope.csv") | Out-Null
    Write-Host "docker end-to-end: OK"
}
finally {
    $ErrorActionPreference = "Continue"
    docker volume rm -f $vol 2>&1 | Out-Null
}

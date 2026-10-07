# get-iso.ps1 - download the latest MeccanicOS ISO in one step (Windows PowerShell).
#
#   irm https://raw.githubusercontent.com/unofficialtools/meccanicos/main/scripts/get-iso.ps1 | iex
#
# The same as get-iso.sh: every part, checked against SHA256SUMS, joined into
# the .iso in the current folder, the .iso checked, the parts deleted. Run it
# again after an interruption: parts already downloaded are kept.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # much faster downloads
$base = if ($env:MECCANICOS_RELEASE) { $env:MECCANICOS_RELEASE } else { "https://github.com/unofficialtools/meccanicos/releases/download/latest" }

Invoke-WebRequest "$base/SHA256SUMS" -OutFile SHA256SUMS
$sums = @{}
foreach ($line in Get-Content SHA256SUMS) {
    $f = $line -split "\s+", 2
    if ($f.Count -eq 2) { $sums[$f[1]] = $f[0] }
}
function Test-Sum($name) {
    (Test-Path $name) -and ((Get-FileHash $name -Algorithm SHA256).Hash.ToLower() -eq $sums[$name])
}

$iso = $sums.Keys | Where-Object { $_ -like "*.iso" } | Select-Object -First 1
if (-not $iso) { throw "no .iso listed in SHA256SUMS" }
if (Test-Sum $iso) { Write-Host "$iso is already here and checks out."; return }

$parts = $sums.Keys | Where-Object { $_ -match "\.iso\.part\d+$" } | Sort-Object
foreach ($part in $parts) {
    if (Test-Sum $part) { Write-Host "${part}: already downloaded"; continue }
    Write-Host "${part}: downloading..."
    Invoke-WebRequest "$base/$part" -OutFile $part
    if (-not (Test-Sum $part)) { throw "$part does not match SHA256SUMS; run again" }
}

Write-Host "Joining the parts into $iso..."
$out = [System.IO.File]::Create((Join-Path $PWD $iso))
try {
    foreach ($part in $parts) {
        $in = [System.IO.File]::OpenRead((Join-Path $PWD $part))
        try { $in.CopyTo($out) } finally { $in.Close() }
    }
} finally { $out.Close() }
if (-not (Test-Sum $iso)) { throw "the joined $iso does not match SHA256SUMS" }
Remove-Item $parts
Write-Host "Done: $iso (checked). Next: write it to a USB stick with Rufus (DD mode; see the README)."

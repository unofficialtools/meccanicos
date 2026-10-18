# get-iso.ps1 - download the latest MeccanicOS ISO in one step (Windows PowerShell).
#
#   irm https://raw.githubusercontent.com/unofficialtools/meccanicos/main/scripts/get-iso.ps1 | iex
#
# The same as get-iso.sh: every part, checked against SHA256SUMS, joined (exactly
# the parts SHA256SUMS lists, in order) into the .iso in the current folder, the
# .iso checked before it replaces anything, the parts deleted. Run it
# again after an interruption: parts already downloaded are kept.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # much faster downloads
$base = if ($env:MECCANICOS_RELEASE) { $env:MECCANICOS_RELEASE } else { "https://github.com/unofficialtools/meccanicos/releases/download/latest" }

# SHA256SUMS, checked before it is used: "SHA256  NAME" lines, plain file
# names (no folders, no "..", none starting with "-"), each once. It replaces
# the SHA256SUMS here once it names an ISO and its parts.
$new = "SHA256SUMS.download"
Invoke-WebRequest "$base/SHA256SUMS" -OutFile $new
try {
    $sums = @{}
    $order = @()
    $n = 0
    foreach ($line in Get-Content -LiteralPath $new) {
        $n++
        if ($line.Trim() -eq "") { continue }
        $f = $line.Trim() -split "\s+"
        if ($f.Count -ne 2) { throw "SHA256SUMS line ${n}: not `"SHA256  NAME`"" }
        $hash = $f[0].ToLower(); $name = $f[1] -replace "^\*", ""
        if ($hash -notmatch "^[0-9a-f]{64}$") { throw "SHA256SUMS line ${n}: not a SHA256: $($f[0])" }
        if ($name -eq "" -or $name -match "[/\\]" -or $name.Contains("..") -or $name.StartsWith("-")) {
            throw "SHA256SUMS line ${n}: not a plain file name: $name"
        }
        if ($sums.ContainsKey($name)) { throw "SHA256SUMS line ${n}: $name is listed twice" }
        $sums[$name] = $hash
        $order += $name
    }
    $iso = $order | Where-Object { $_ -like "*.iso" } | Select-Object -First 1
    if (-not $iso) { throw "no .iso listed in SHA256SUMS" }
    # Exactly this ISO's parts, in order (ISO.part01, ISO.part02, ...).
    $parts = @($order | Where-Object { $_.StartsWith("$iso.part") -and $_.Substring($iso.Length + 5) -match "^\d+$" } |
        Sort-Object { [int64]$_.Substring($iso.Length + 5) })
    if ($parts.Count -eq 0) { throw "SHA256SUMS lists no parts of $iso" }
    $numbers = $parts | ForEach-Object { [int64]$_.Substring($iso.Length + 5) }
    if (@($numbers | Select-Object -Unique).Count -ne $parts.Count) { throw "SHA256SUMS lists a part of $iso twice" }
    Move-Item -Force -LiteralPath $new -Destination SHA256SUMS
} finally {
    if (Test-Path -LiteralPath $new) { Remove-Item -LiteralPath $new }
}
function Test-Sum($name) {
    (Test-Path -LiteralPath $name) -and ((Get-FileHash -LiteralPath $name -Algorithm SHA256).Hash.ToLower() -eq $sums[$name])
}
if (Test-Sum $iso) { Write-Host "$iso is already here and checks out."; return }

foreach ($part in $parts) {
    if (Test-Sum $part) { Write-Host "${part}: already downloaded"; continue }
    Write-Host "${part}: downloading..."
    Invoke-WebRequest "$base/$part" -OutFile $part
    if (-not (Test-Sum $part)) { throw "$part does not match SHA256SUMS; run again" }
}

Write-Host "Joining the parts into $iso..."
# Into a file of its own, moved into place once checked.
$joined = "$iso.joining"
$out = [System.IO.File]::Create((Join-Path $PWD $joined))
try {
    foreach ($part in $parts) {
        $in = [System.IO.File]::OpenRead((Join-Path $PWD $part))
        try { $in.CopyTo($out) } finally { $in.Close() }
    }
} finally { $out.Close() }
if ((Get-FileHash -LiteralPath $joined -Algorithm SHA256).Hash.ToLower() -ne $sums[$iso]) {
    Remove-Item -LiteralPath $joined
    throw "the joined $iso does not match SHA256SUMS"
}
Move-Item -Force -LiteralPath $joined -Destination $iso
Remove-Item -LiteralPath $parts
Write-Host "Done: $iso (checked). Next: write it to a USB stick with Rufus (DD mode; see the README)."

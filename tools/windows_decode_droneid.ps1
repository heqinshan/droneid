param(
    [Parameter(Mandatory = $true)]
    [string]$InputFile,

    [string]$Python = "D:\anconda3\envs\sdr\python.exe",
    [double]$SampleRate = 15360000,
    [ValidateSet("fc32", "sc16")]
    [string]$SampleType = "fc32",
    [string]$DroneSecuritySrc = "",
    [string]$OutDir = "",
    [string]$LinearRotations = "0",
    [string]$SampleOffsets = "0",
    [string]$Tunes = "0",
    [string]$Phases = "0,1,2,3"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$decoder = Join-Path $repoRoot "tools\windows_droneid_decode.py"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python not found: $Python"
}
if (-not (Test-Path -LiteralPath $InputFile)) {
    throw "Input IQ file not found: $InputFile"
}
if ([string]::IsNullOrWhiteSpace($DroneSecuritySrc)) {
    $DroneSecuritySrc = Join-Path $repoRoot "dronesecurity"
}
if (-not (Test-Path -LiteralPath $DroneSecuritySrc)) {
    throw "DroneSecurity src not found: $DroneSecuritySrc"
}
if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutDir = Join-Path (Split-Path $InputFile -Parent) "decode_out"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

& $Python $decoder `
    --input $InputFile `
    --sample-rate $SampleRate `
    --sample-type $SampleType `
    --dronesecurity-src $DroneSecuritySrc `
    --out-dir $OutDir `
    --linear-rotations $LinearRotations `
    --sample-offsets $SampleOffsets `
    --tunes $Tunes `
    --phases $Phases

exit $LASTEXITCODE

param(
  [Parameter(Mandatory=$true)][string]$Bundle,
  [string]$DriveMedic,
  [string]$NetMedic,
  [string]$EvidenceHome = $(if ($env:FIELDMEDIC_HOME) { $env:FIELDMEDIC_HOME } else { Join-Path $env:LOCALAPPDATA 'FieldMedic' })
)

$ErrorActionPreference = 'Stop'

function Resolve-Python311 {
  $candidates = @(
    @{ Exe = 'py'; Args = @('-3.13') },
    @{ Exe = 'py'; Args = @('-3.12') },
    @{ Exe = 'py'; Args = @('-3.11') },
    @{ Exe = 'python'; Args = @() }
  )
  foreach ($candidate in $candidates) {
    try {
      $candidateArgs = @($candidate.Args)
      & $candidate.Exe @candidateArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" *> $null
      if ($LASTEXITCODE -eq 0) { return $candidate }
    } catch { }
  }
  throw 'Python 3.11+ was not found.'
}

$bundlePath = (Resolve-Path $Bundle).Path
$python = Resolve-Python311
$tempRoot = Join-Path $env:TEMP ('fieldmedic-smoke-' + [guid]::NewGuid().ToString('N'))
$extractRoot = Join-Path $tempRoot 'bundle'
$installRoot = Join-Path $tempRoot 'program'
$dataRoot = Join-Path $tempRoot 'data'
$dashboardPath = Join-Path $tempRoot 'dashboard.html'
$releasePath = Join-Path $tempRoot 'release.json'
$sentinel = Join-Path $dataRoot 'preserve-me.txt'

$discoverPass = $false
$dashboardPass = $false
$releasePass = $false
$uninstallPass = $false
$dataPreserved = $false
$sentinelPreserved = $false
$installReceiptSha = ''
$wheelPath = $null

New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
New-Item -ItemType Directory -Force -Path $EvidenceHome | Out-Null

try {
  Expand-Archive -LiteralPath $bundlePath -DestinationPath $extractRoot -Force
  $wheels = @(Get-ChildItem -Path (Join-Path $extractRoot 'packages') -Filter 'fieldmedic-*.whl' -File)
  if ($wheels.Count -ne 1) { throw "Expected exactly one FieldMedic wheel; found $($wheels.Count)." }
  $wheelPath = $wheels[0].FullName

  $installArgs = @('-InstallRoot', $installRoot, '-DataRoot', $dataRoot)
  if ($DriveMedic) { $installArgs += @('-DriveMedic', $DriveMedic) }
  if ($NetMedic) { $installArgs += @('-NetMedic', $NetMedic) }
  & (Join-Path $extractRoot 'install.ps1') @installArgs
  if ($LASTEXITCODE -ne 0) { throw 'RC4 smoke installation failed.' }

  $launcher = Join-Path $installRoot 'bin\fieldmedic.cmd'
  if (-not (Test-Path $launcher)) { throw 'Installed FieldMedic launcher is missing.' }

  & $launcher discover *> $null
  $discoverPass = ($LASTEXITCODE -eq 0)

  & $launcher dashboard --output $dashboardPath *> $null
  $dashboardPass = (($LASTEXITCODE -eq 0) -and (Test-Path $dashboardPath))

  & $launcher release-receipt --output $releasePath *> $null
  $releasePass = (($LASTEXITCODE -eq 0) -and (Test-Path $releasePath))

  $installReceiptPath = Join-Path $dataRoot 'installation\install.json'
  if (-not (Test-Path $installReceiptPath)) { throw 'Install receipt missing after smoke install.' }
  $installReceipt = Get-Content -Raw $installReceiptPath | ConvertFrom-Json
  $installReceiptSha = [string]$installReceipt.receipt_sha256
  if (-not $installReceiptSha) { throw 'Install receipt SHA-256 missing.' }

  Set-Content -Path $sentinel -Value 'FieldMedic default uninstall must preserve this file.' -Encoding UTF8

  $uninstaller = Join-Path $installRoot 'uninstall.ps1'
  & $uninstaller -InstallRoot $installRoot -DataRoot $dataRoot *> $null
  $uninstallPass = (($LASTEXITCODE -eq 0) -and -not (Test-Path $installRoot))
  $dataPreserved = (Test-Path $dataRoot)
  $sentinelPreserved = (Test-Path $sentinel)
} finally {
  if (-not $wheelPath) {
    $candidate = Get-ChildItem -Path (Join-Path $extractRoot 'packages') -Filter 'fieldmedic-*.whl' -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($candidate) { $wheelPath = $candidate.FullName }
  }

  if ($wheelPath) {
    $out = Join-Path $EvidenceHome 'qualification\windows-install-smoke\latest.json'
    $writer = Join-Path $extractRoot 'write-install-smoke-receipt.py'
    $writerArgs = @(
      $writer,
      '--wheel', $wheelPath,
      '--output', $out,
      '--bundle', $bundlePath,
      '--install-root', $installRoot,
      '--data-root', $dataRoot,
      '--install-receipt-sha256', $installReceiptSha,
      '--discover-pass', $discoverPass.ToString().ToLowerInvariant(),
      '--dashboard-pass', $dashboardPass.ToString().ToLowerInvariant(),
      '--release-receipt-pass', $releasePass.ToString().ToLowerInvariant(),
      '--default-uninstall-pass', $uninstallPass.ToString().ToLowerInvariant(),
      '--data-preserved', $dataPreserved.ToString().ToLowerInvariant(),
      '--sentinel-preserved', $sentinelPreserved.ToString().ToLowerInvariant()
    )
    $pyArgs = @($python.Args)
    & $python.Exe @pyArgs @writerArgs
    $receiptExit = $LASTEXITCODE
  } else {
    $receiptExit = 2
  }

  if (Test-Path $tempRoot) { Remove-Item -Recurse -Force $tempRoot -ErrorAction SilentlyContinue }
}

if ($receiptExit -ne 0) { throw 'FieldMedic Windows install smoke did not PASS.' }
Write-Host 'FieldMedic Windows install/default-uninstall smoke PASS.' -ForegroundColor Green
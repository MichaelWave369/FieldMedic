param(
  [Parameter(Mandatory=$true)][string]$BundleRoot,
  [Parameter(Mandatory=$true)][string]$DriveMedic,
  [Parameter(Mandatory=$true)][string]$NetMedic,
  [string]$ReceiptHome = (Join-Path $env:LOCALAPPDATA 'FieldMedic')
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Windows install smoke must run on Windows.' }

$bundle = [IO.Path]::GetFullPath($BundleRoot)
$installer = Join-Path $bundle 'install.ps1'
$uninstaller = Join-Path $bundle 'uninstall.ps1'
if (-not (Test-Path $installer -PathType Leaf)) { throw 'Bundle install.ps1 not found.' }
if (-not (Test-Path $uninstaller -PathType Leaf)) { throw 'Bundle uninstall.ps1 not found.' }
if (-not (Test-Path $DriveMedic -PathType Leaf)) { throw 'DriveMedic binary not found.' }
if (-not (Test-Path $NetMedic -PathType Leaf)) { throw 'NetMedic binary not found.' }

$id = [guid]::NewGuid().ToString('N').Substring(0,12)
$installRoot = Join-Path $env:LOCALAPPDATA "Programs\FieldMedic-Qualification\$id"
$dataRoot = Join-Path $env:LOCALAPPDATA "FieldMedic-Qualification\$id"
$workRoot = Join-Path $env:TEMP "FieldMedic-Install-Smoke-$id"
New-Item -ItemType Directory -Force -Path $workRoot | Out-Null

$firstReceipt = Join-Path $workRoot 'first-install.json'
$secondReceipt = Join-Path $workRoot 'second-install.json'
$observationPath = Join-Path $workRoot 'observation.json'
$output = Join-Path $ReceiptHome 'qualification\windows-install-smoke\latest.json'
$sentinel = Join-Path $dataRoot 'qualification-sentinel.txt'
$sentinelText = "FieldMedic installer preservation sentinel $id"

try {
  & $installer -DriveMedic $DriveMedic -NetMedic $NetMedic -InstallRoot $installRoot -DataRoot $dataRoot
  if ($LASTEXITCODE -ne 0) { throw 'First isolated FieldMedic install failed.' }

  $installedCli = Join-Path $installRoot 'bin\fieldmedic.cmd'
  if (-not (Test-Path $installedCli -PathType Leaf)) { throw 'Installed FieldMedic launcher missing.' }
  $receiptPath = Join-Path $dataRoot 'installation\install.json'
  if (-not (Test-Path $receiptPath -PathType Leaf)) { throw 'First install receipt missing.' }
  Copy-Item -Force $receiptPath $firstReceipt

  Set-Content -Path $sentinel -Value $sentinelText -Encoding UTF8
  $shaBefore = (Get-FileHash -Algorithm SHA256 $sentinel).Hash.ToLowerInvariant()

  & $uninstaller -InstallRoot $installRoot -DataRoot $dataRoot
  if ($LASTEXITCODE -ne 0) { throw 'Default uninstall failed.' }
  $programRemoved = -not (Test-Path $installRoot)
  $dataPreserved = Test-Path $dataRoot -PathType Container
  $sentinelAfterUninstall = Test-Path $sentinel -PathType Leaf
  $shaAfterUninstall = if ($sentinelAfterUninstall) { (Get-FileHash -Algorithm SHA256 $sentinel).Hash.ToLowerInvariant() } else { '' }

  & $installer -DriveMedic $DriveMedic -NetMedic $NetMedic -InstallRoot $installRoot -DataRoot $dataRoot
  if ($LASTEXITCODE -ne 0) { throw 'Reinstall after default uninstall failed.' }
  if (-not (Test-Path $receiptPath -PathType Leaf)) { throw 'Second install receipt missing.' }
  Copy-Item -Force $receiptPath $secondReceipt

  $sentinelAfterReinstall = Test-Path $sentinel -PathType Leaf
  $shaAfterReinstall = if ($sentinelAfterReinstall) { (Get-FileHash -Algorithm SHA256 $sentinel).Hash.ToLowerInvariant() } else { '' }

  $discoverText = (& $installedCli discover | Out-String).Trim()
  $launcherOk = ($LASTEXITCODE -eq 0)
  $discoveryReady = $false
  if ($launcherOk) {
    try { $discoveryReady = [bool](($discoverText | ConvertFrom-Json).ready_for_diagnostics) } catch { $discoveryReady = $false }
  }

  [pscustomobject]@{
    schema = 'field-medic-windows-install-smoke-observation-v1'
    qualification_id = $id
    default_uninstall_program_removed = [bool]$programRemoved
    default_uninstall_data_preserved = [bool]$dataPreserved
    sentinel_present_after_uninstall = [bool]$sentinelAfterUninstall
    sentinel_present_after_reinstall = [bool]$sentinelAfterReinstall
    sentinel_sha_before = $shaBefore
    sentinel_sha_after_uninstall = $shaAfterUninstall
    sentinel_sha_after_reinstall = $shaAfterReinstall
    reinstall_launcher_ok = [bool]$launcherOk
    reinstall_discovery_ready = [bool]$discoveryReady
  } | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $observationPath

  $runtime = (Get-Content -Raw $secondReceipt | ConvertFrom-Json).runtime_root
  $exe = Join-Path $runtime 'Scripts\fieldmedic.exe'
  if (-not (Test-Path $exe -PathType Leaf)) { throw 'Reinstalled fieldmedic.exe not found.' }
  New-Item -ItemType Directory -Force -Path (Split-Path $output) | Out-Null
  & $exe record-windows-install-smoke --first-install $firstReceipt --second-install $secondReceipt --observation $observationPath --output $output
  if ($LASTEXITCODE -ne 0) { throw 'Install smoke receipt generation failed.' }

  Write-Host ''
  Write-Host 'FIELDMEDIC WINDOWS INSTALL/UNINSTALL SMOKE PASS.' -ForegroundColor Green
  Write-Host "Receipt: $output"
} finally {
  if (Test-Path $installRoot) {
    try { & $uninstaller -InstallRoot $installRoot -DataRoot $dataRoot -RemoveData -ConfirmDataRemoval | Out-Null } catch {}
  } elseif (Test-Path $dataRoot) {
    Remove-Item -Recurse -Force $dataRoot -ErrorAction SilentlyContinue
  }
  Remove-Item -Recurse -Force $workRoot -ErrorAction SilentlyContinue
}
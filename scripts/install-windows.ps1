param(
  [string]$DriveMedic,
  [string]$NetMedic,
  [switch]$AddToPath,
  [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Programs\FieldMedic'),
  [string]$DataRoot = (Join-Path $env:LOCALAPPDATA 'FieldMedic')
)

$ErrorActionPreference = 'Stop'

if (-not $env:LOCALAPPDATA) { throw 'LOCALAPPDATA is required for the per-user FieldMedic installer.' }

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
  throw 'Python 3.11+ was not found. Install Python 3.11 or newer, then rerun this installer.'
}

$bundleRoot = $PSScriptRoot
$manifestPath = Join-Path $bundleRoot 'manifest.json'
if (-not (Test-Path $manifestPath)) { throw 'Bundle manifest.json is missing.' }
$manifest = Get-Content -Raw $manifestPath | ConvertFrom-Json
if ($manifest.schema -ne 'field-medic-windows-bundle-v1') { throw 'Unsupported FieldMedic bundle manifest schema.' }
$bundleFull = [IO.Path]::GetFullPath($bundleRoot).TrimEnd('\') + '\'
foreach ($entry in $manifest.files) {
  $candidatePath = [IO.Path]::GetFullPath((Join-Path $bundleRoot ([string]$entry.path)))
  if (-not $candidatePath.StartsWith($bundleFull, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe bundle manifest path: $($entry.path)"
  }
  if (-not (Test-Path $candidatePath -PathType Leaf)) { throw "Bundle file missing: $($entry.path)" }
  $item = Get-Item $candidatePath
  if ([long]$item.Length -ne [long]$entry.size_bytes) { throw "Bundle size mismatch: $($entry.path)" }
  $actualHash = (Get-FileHash -Algorithm SHA256 $candidatePath).Hash.ToLowerInvariant()
  if ($actualHash -ne ([string]$entry.sha256).ToLowerInvariant()) { throw "Bundle SHA-256 mismatch: $($entry.path)" }
}

$wheels = @(Get-ChildItem -Path (Join-Path $bundleRoot 'packages') -Filter 'fieldmedic-*.whl' -File)
if ($wheels.Count -ne 1) { throw "Expected exactly one FieldMedic wheel in packages\; found $($wheels.Count)." }
$wheel = $wheels[0]
$match = [regex]::Match($wheel.Name, '^fieldmedic-(?<version>.+?)-py3-none-any\.whl$', 'IgnoreCase')
if (-not $match.Success) { throw "Could not parse FieldMedic version from wheel name: $($wheel.Name)" }
$version = $match.Groups['version'].Value

$python = Resolve-Python311
$runtimeId = "$version-$([guid]::NewGuid().ToString('N').Substring(0,8))"
$runtimeRoot = Join-Path $InstallRoot (Join-Path 'runtimes' $runtimeId)
$binRoot = Join-Path $InstallRoot 'bin'
$fieldmedicExe = Join-Path $runtimeRoot 'Scripts\fieldmedic.exe'
$launcher = Join-Path $binRoot 'fieldmedic.cmd'
$dashboardLauncher = Join-Path $binRoot 'fieldmedic-dashboard.cmd'
$uninstaller = Join-Path $InstallRoot 'uninstall.ps1'

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path $binRoot | Out-Null
New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null

$pathAdded = $false
$oldLauncher = if (Test-Path $launcher) { Get-Content -Raw $launcher } else { $null }
$oldDashboardLauncher = if (Test-Path $dashboardLauncher) { Get-Content -Raw $dashboardLauncher } else { $null }
$oldUninstaller = if (Test-Path $uninstaller) { Get-Content -Raw $uninstaller } else { $null }
$configPath = Join-Path $DataRoot 'config\engines.json'
$oldConfig = if (Test-Path $configPath) { Get-Content -Raw $configPath } else { $null }

try {
  $pythonArgs = @($python.Args)
  & $python.Exe @pythonArgs -m venv $runtimeRoot
  if ($LASTEXITCODE -ne 0) { throw 'Failed to create FieldMedic runtime.' }

  $runtimePython = Join-Path $runtimeRoot 'Scripts\python.exe'
  & $runtimePython -m pip install --disable-pip-version-check --no-index --no-deps $wheel.FullName
  if ($LASTEXITCODE -ne 0) { throw 'Failed to install FieldMedic wheel into the new runtime.' }
  if (-not (Test-Path $fieldmedicExe)) { throw 'Installed runtime did not produce fieldmedic.exe.' }

  $env:FIELDMEDIC_HOME = $DataRoot

  if ($DriveMedic -or $NetMedic) {
    $cfgArgs = @('configure-engines')
    if ($DriveMedic) { $cfgArgs += @('--drivemedic', $DriveMedic) }
    if ($NetMedic) { $cfgArgs += @('--netmedic', $NetMedic) }
    & $fieldmedicExe @cfgArgs | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Engine handoff configuration failed.' }
  }

  & $fieldmedicExe discover | Out-Host
  if ($LASTEXITCODE -ne 0) { throw 'FieldMedic discovery smoke check failed.' }

  $launcherText = @"
@echo off
if "%FIELDMEDIC_HOME%"=="" set "FIELDMEDIC_HOME=$DataRoot"
"$fieldmedicExe" %*
"@
  Set-Content -Path $launcher -Value $launcherText -Encoding ASCII

  $dashboardPath = Join-Path $DataRoot 'dashboard\fieldmedic-dashboard.html'
  $dashboardText = @"
@echo off
if "%FIELDMEDIC_HOME%"=="" set "FIELDMEDIC_HOME=$DataRoot"
"$fieldmedicExe" dashboard --output "$dashboardPath"
if errorlevel 1 exit /b %errorlevel%
start "" "$dashboardPath"
"@
  Set-Content -Path $dashboardLauncher -Value $dashboardText -Encoding ASCII

  Copy-Item -Force (Join-Path $bundleRoot 'uninstall.ps1') $uninstaller

  if ($AddToPath) {
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $parts = @($userPath -split ';' | Where-Object { $_ -and $_.Trim() })
    $already = $parts | Where-Object { $_.TrimEnd('\') -ieq $binRoot.TrimEnd('\') }
    if (-not $already) {
      $newPath = (($parts + $binRoot) -join ';')
      [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
      $pathAdded = $true
    }
  }

  $receiptArgs = @(
    'installation-receipt',
    '--install-root', $InstallRoot,
    '--runtime-root', $runtimeRoot,
    '--wheel', $wheel.FullName,
    '--launcher', $launcher,
    '--dashboard-launcher', $dashboardLauncher,
    '--uninstaller', $uninstaller
  )
  if ($pathAdded) { $receiptArgs += '--path-added' }
  & $fieldmedicExe @receiptArgs | Out-Host
  if ($LASTEXITCODE -ne 0) { throw 'Installation receipt generation failed.' }

  Write-Host ''
  Write-Host "FieldMedic $version installed successfully." -ForegroundColor Green
  Write-Host "Program: $InstallRoot"
  Write-Host "Data:    $DataRoot"
  Write-Host "CLI:     $launcher"
  Write-Host "Dashboard: $dashboardLauncher"
  if ($AddToPath -and -not $pathAdded) { Write-Host 'FieldMedic bin directory was already on the user PATH.' }
  if ($pathAdded) { Write-Host 'FieldMedic bin directory was added to the user PATH. Open a new terminal to use it.' }
} catch {
  Write-Warning "Installation failed: $($_.Exception.Message)"
  if (Test-Path $runtimeRoot) { Remove-Item -Recurse -Force $runtimeRoot -ErrorAction SilentlyContinue }
  throw
}
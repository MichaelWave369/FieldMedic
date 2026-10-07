param(
  [switch]$RemoveData,
  [switch]$ConfirmDataRemoval,
  [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Programs\FieldMedic'),
  [string]$DataRoot = (Join-Path $env:LOCALAPPDATA 'FieldMedic')
)

$ErrorActionPreference = 'Stop'

if ($RemoveData -and -not $ConfirmDataRemoval) {
  throw 'Data removal requires both -RemoveData and -ConfirmDataRemoval.'
}

$binRoot = Join-Path $InstallRoot 'bin'
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath) {
  $parts = @($userPath -split ';' | Where-Object { $_ -and $_.Trim() })
  $filtered = @($parts | Where-Object { $_.TrimEnd('\') -ine $binRoot.TrimEnd('\') })
  if ($filtered.Count -ne $parts.Count) {
    [Environment]::SetEnvironmentVariable('Path', ($filtered -join ';'), 'User')
  }
}

if (Test-Path $InstallRoot) {
  Remove-Item -Recurse -Force $InstallRoot
}

if ($RemoveData) {
  if (Test-Path $DataRoot) { Remove-Item -Recurse -Force $DataRoot }
  Write-Host 'FieldMedic program and local data removed.' -ForegroundColor Yellow
} else {
  Write-Host 'FieldMedic program removed. Local diagnostic data was preserved.' -ForegroundColor Green
  Write-Host "Preserved data: $DataRoot"
}
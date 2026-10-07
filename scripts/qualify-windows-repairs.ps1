param(
  [Parameter(Mandatory=$true)][int]$InterfaceIndex,
  [ValidateSet("IPv4","IPv6")][string]$AddressFamily = "IPv4",
  [Parameter(Mandatory=$true)][int]$TemporaryMetric,
  [Parameter(Mandatory=$true)][string]$Operator,
  [string]$DriveMedic = $env:DRIVEMEDIC_BIN,
  [string]$NetMedic = $env:NETMEDIC_BIN
)

$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
  throw "FieldMedic live repair qualification must run in an elevated Administrator PowerShell."
}

$args = @(
  "qualify-windows-repairs",
  "--interface-index", "$InterfaceIndex",
  "--address-family", $AddressFamily,
  "--temporary-metric", "$TemporaryMetric",
  "--operator", $Operator
)
if ($DriveMedic) { $args += @("--drivemedic", $DriveMedic) }
if ($NetMedic) { $args += @("--netmedic", $NetMedic) }

& fieldmedic @args
if ($LASTEXITCODE -ne 0) {
  throw "FieldMedic Windows repair qualification failed with exit code $LASTEXITCODE"
}

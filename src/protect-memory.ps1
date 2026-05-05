param(
  [switch]$DisableServices,
  [switch]$KillNonAgentNode
)

$ErrorActionPreference = 'Continue'

function Remove-RunValue {
  param([string]$Path, [string]$Name)
  if (Get-ItemProperty -Path $Path -Name $Name -ErrorAction SilentlyContinue) {
    Remove-ItemProperty -Path $Path -Name $Name -ErrorAction SilentlyContinue
    Write-Host "Removed startup: $Path -> $Name"
  }
}

function Disable-Task {
  param([string]$TaskName)
  Write-Host "Disabling task: $TaskName"
  schtasks.exe /Change /TN $TaskName /DISABLE | Out-Host
}

function Set-ServiceStartup {
  param([string]$Name, [string]$Mode)
  $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
  if ($svc) {
    Stop-Service -Name $Name -Force -ErrorAction SilentlyContinue
    Set-Service -Name $Name -StartupType $Mode -ErrorAction SilentlyContinue
    Write-Host "Service $Name -> $Mode"
  }
}

$hkcuRun = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$hklmRun = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run'
$wowRun = 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run'

foreach ($name in @(
  'GogGalaxy',
  'Surfshark',
  'NordVPN',
  'Docker Desktop',
  'Teams',
  'Polar FlowSync',
  'Adobe Acrobat Synchronizer'
)) {
  Remove-RunValue $hkcuRun $name
}

foreach ($name in @('AdobeGCInvoker-1.0')) {
  Remove-RunValue $hklmRun $name
}

foreach ($name in @('Adobe CCXProcess', 'Adobe Creative Cloud')) {
  Remove-RunValue $wowRun $name
}

foreach ($task in @(
  '\Adobe Acrobat Update Task',
  '\Adobe-Genuine-Software-Integrity-Scheduler-1.0',
  '\AdobeGCInvoker-1.0',
  '\Launch Adobe CCXProcess',
  '\KnowledgeOptimizer-Ollama-Warm'
)) {
  Disable-Task $task
}

if ($DisableServices) {
  foreach ($svc in @(
    'AdobeARMservice',
    'AdobeUpdateService',
    'NordUpdaterService',
    'nordvpn-service',
    'nordsec-threatprotection-service',
    'Surfshark Service'
  )) {
    Set-ServiceStartup $svc Disabled
  }

  foreach ($svc in @(
    'GalaxyClientService',
    'GalaxyCommunication',
    'com.docker.service'
  )) {
    Set-ServiceStartup $svc Manual
  }
}

foreach ($pname in @(
  'Creative Cloud',
  'Creative Cloud Helper',
  'Creative Cloud UI Helper',
  'CoreSync',
  'Adobe Desktop Service',
  'AdobeIPCBroker',
  'CCXProcess',
  'AdobeCollabSync',
  'AGCInvokerUtility',
  'GogGalaxy',
  'GalaxyClient',
  'Surfshark',
  'NordVPN',
  'ollama'
)) {
  Get-Process -Name $pname -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue
}

if ($KillNonAgentNode) {
  Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class NtProcGuard {
  [DllImport("ntdll.dll")] public static extern int NtQueryInformationProcess(IntPtr h, int c, ref PROCESS_BASIC_INFORMATION p, int l, out int r);
  [StructLayout(LayoutKind.Sequential)] public struct PROCESS_BASIC_INFORMATION { public IntPtr Reserved1; public IntPtr PebBaseAddress; public IntPtr Reserved2_0; public IntPtr Reserved2_1; public IntPtr UniqueProcessId; public IntPtr InheritedFromUniqueProcessId; }
  public static int ParentId(IntPtr handle) { var p = new PROCESS_BASIC_INFORMATION(); int r; int s = NtQueryInformationProcess(handle, 0, ref p, System.Runtime.InteropServices.Marshal.SizeOf(p), out r); return s == 0 ? p.InheritedFromUniqueProcessId.ToInt32() : -1; }
}
'@
  $all = Get-Process | Select-Object Id,Name,Path,@{Name='ParentId';Expression={[NtProcGuard]::ParentId($_.Handle)}}
  $byId = @{}
  $all | ForEach-Object { $byId[$_.Id] = $_ }

  function Get-ChainText($p) {
    $seen = @{}
    $cur = $p
    $chain = @($cur.Name + ':' + $cur.Id)
    while ($cur.ParentId -and $byId.ContainsKey($cur.ParentId) -and -not $seen.ContainsKey($cur.ParentId)) {
      $seen[$cur.Id] = $true
      $cur = $byId[$cur.ParentId]
      $chain += ($cur.Name + ':' + $cur.Id)
      if ($chain.Count -gt 30) { break }
    }
    return ($chain -join ' <- ')
  }

  $keepPattern = '(?i)codex|antigravity|language_server_windows_x64|obsidian'
  foreach ($node in ($all | Where-Object Name -eq 'node')) {
    $chain = Get-ChainText $node
    if ($chain -notmatch $keepPattern) {
      Write-Host "Stopping non-agent node $($node.Id): $chain"
      Stop-Process -Id $node.Id -Force -ErrorAction SilentlyContinue
    }
  }
}

Write-Host "`nCurrent top memory groups:"
Get-Process |
  Group-Object Name |
  ForEach-Object {
    [pscustomobject]@{
      Name = $_.Name
      Count = $_.Count
      MemoryMB = [math]::Round(($_.Group | Measure-Object WorkingSet64 -Sum).Sum / 1MB, 1)
    }
  } |
  Sort-Object MemoryMB -Descending |
  Select-Object -First 15 |
  Format-Table -AutoSize

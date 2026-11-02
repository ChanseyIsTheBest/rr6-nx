# rr6-nx (2026-11-03): waits for a free slot, then one tools/run_ryujinx.ps1 run. The limits are the user's: at most two Ryujinx across all
# ports, 6 GB or more of free commit memory. It only looks at other ports' runs and never touches them. Gives up after -WaitMinutes.
#   powershell -File tools/run_ryujinx_when_free.ps1 -Seconds 480 -Name emu2 -Toml out\emu2.toml [-WaitMinutes 60]
param([int]$Seconds = 480, [string]$Name = "emu", [string]$Toml = "", [int]$WaitMinutes = 60, [double]$MinCommitGB = 6)
$root = Split-Path -Parent $PSScriptRoot
$deadline = (Get-Date).AddMinutes($WaitMinutes)
while ($true) {
    $running = @(Get-Process -Name Ryujinx -ErrorAction SilentlyContinue).Count
    $free = (Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory / 1MB
    if ($running -lt 2 -and $free -ge $MinCommitGB) { break }
    if ((Get-Date) -gt $deadline) { Write-Output ("gave up after {0} min: {1} Ryujinx running, {2:N1} GB free" -f $WaitMinutes, $running, $free); exit 5 }
    Start-Sleep -Seconds 20
}
Write-Output ("{0}: starting, {1} Ryujinx running, {2:N1} GB free" -f (Get-Date -Format HH:mm), $running, $free)
& (Join-Path $root "tools\run_ryujinx.ps1") -Seconds $Seconds -Name $Name -Toml $Toml -MinCommitGB $MinCommitGB | Select-Object -First 3
Write-Output ("{0}: done" -f (Get-Date -Format HH:mm))

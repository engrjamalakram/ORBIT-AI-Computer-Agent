# Registers ORBIT's auto-start + watchdog tasks. Needs admin (the .bat elevates for you).
$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "  Installing ORBIT auto-start from: $dir"
Write-Host ""

# Laptop-critical: by default Windows refuses to start tasks on battery and kills them
# when you unplug. These settings keep her alive through a power cut.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

# 1) start at logon (no artificial delay, unlike the Startup folder)
$action1 = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "`"$dir\lappilot-hidden.vbs`"" -WorkingDirectory $dir
$trigger1 = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "ORBIT" -Action $action1 -Trigger $trigger1 `
    -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "  [1/2] 'ORBIT'          - starts at logon"

# 2) watchdog every 3 minutes: brings her back after a crash, outage or reboot
$action2 = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "`"$dir\watchdog.vbs`"" -WorkingDirectory $dir
$trigger2 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 3) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "ORBIT Watchdog" -Action $action2 -Trigger $trigger2 `
    -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "  [2/2] 'ORBIT Watchdog' - checks every 3 minutes"

# Belt and braces: keep a Startup-folder shortcut too, so she still starts at logon
# even if the scheduled tasks are ever wiped.
$link = Join-Path ([Environment]::GetFolderPath('Startup')) 'ORBIT.lnk'
$w = New-Object -ComObject WScript.Shell
$s = $w.CreateShortcut($link)
$s.TargetPath = 'wscript.exe'
$s.Arguments = "`"$dir\lappilot-hidden.vbs`""
$s.WorkingDirectory = $dir
$s.Description = 'ORBIT laptop agent'
$s.Save()
Write-Host "  [+]   Startup-folder backup shortcut in place"

Write-Host ""
Write-Host "  Verifying..."
foreach ($n in @("ORBIT", "ORBIT Watchdog")) {
    $t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
    if ($t) { Write-Host "    OK  $n  [$($t.State)]" } else { Write-Host "    !!  $n MISSING" }
}

Write-Host ""
Write-Host "  Starting her now if she is not already running..."
Start-Process wscript.exe -ArgumentList "`"$dir\watchdog.vbs`"" -WorkingDirectory $dir
Write-Host ""

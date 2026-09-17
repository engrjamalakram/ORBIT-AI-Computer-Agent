' ORBIT watchdog - runs every few minutes.
' Cheap WMI check first: only launches if she is NOT already running, so it costs
' almost nothing when everything is healthy. This is what brings her back after a
' crash, a network outage, or a reboot - with nobody touching the laptop.

Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)

running = False
On Error Resume Next
Set wmi = GetObject("winmgmts:\\.\root\cimv2")
If Err.Number = 0 Then
    Set procs = wmi.ExecQuery( _
        "SELECT ProcessId FROM Win32_Process WHERE Name = 'python.exe' AND CommandLine LIKE '%agent.main%'")
    If Err.Number = 0 Then
        If procs.Count > 0 Then running = True
    End If
End If
On Error GoTo 0

If Not running Then
    Set shell = CreateObject("WScript.Shell")
    shell.CurrentDirectory = here
    shell.Run """" & here & "\run.bat""", 0, False
End If

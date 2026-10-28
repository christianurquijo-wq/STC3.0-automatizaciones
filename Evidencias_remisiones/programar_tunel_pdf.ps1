# Programa el tunel de PDF de Remisiones para que arranque solo al iniciar sesion en Windows.
# Uso (PowerShell, desde KuepaProyects):  .\STC\Evidencias_remisiones\programar_tunel_pdf.ps1
# Quitarlo:  Unregister-ScheduledTask -TaskName "Kuepa - Tunel PDF" -Confirm:$false
$ErrorActionPreference = "Stop"
$script  = Join-Path $PSScriptRoot "tunel_pdf.py"
$stc     = Split-Path $PSScriptRoot -Parent
$pythonw = "C:\venvs\stc\Scripts\pythonw.exe"   # pythonw = sin ventana de consola
if (-not (Test-Path $pythonw)) { throw "No existe $pythonw (venv de STC)." }

$accion     = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$script`"" -WorkingDirectory $stc
$disparador = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal  = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$ajustes    = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 5) `
                -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "Kuepa - Tunel PDF" -Action $accion -Trigger $disparador `
    -Principal $principal -Settings $ajustes -Force | Out-Null
Start-ScheduledTask -TaskName "Kuepa - Tunel PDF"
Write-Host "Tarea 'Kuepa - Tunel PDF' creada e iniciada. Registro: $stc\logs\tunel_pdf.log"

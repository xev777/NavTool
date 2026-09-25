<#
.SYNOPSIS
    Instala TrafficBar en «Archivos de programa», una carpeta que solo un administrador puede modificar.

.DESCRIPTION
    Por qué importa: TrafficBar pide permisos de administrador para capturar el tráfico (Npcap).
    Si el programa vive en una carpeta que cualquier proceso de tu usuario puede modificar,
    ese proceso podría cambiar los archivos de TrafficBar y ejecutarse con permisos elevados
    la próxima vez que aceptes el aviso de UAC. En «Archivos de programa» eso no es posible.

    Qué hace:
      1. Se relanza como administrador (te saldrá el aviso de UAC una sola vez).
      2. Copia la carpeta dist\TrafficBar a C:\Program Files\TrafficBar.
      3. Comprueba los permisos: si el grupo «Users» pudiera escribir ahí, lo corrige.
      4. Crea un acceso directo en el menú Inicio.
      5. (Opcional) -InicioConWindows: TrafficBar arranca al iniciar sesión, oculto en la bandeja.
    No toca tu configuración ni tu historial (están en %LOCALAPPDATA%\TrafficBar).

.PARAMETER Origen
    Carpeta con TrafficBar.exe (por defecto: dist\TrafficBar junto a este script).
.PARAMETER InicioConWindows
    Añade TrafficBar al inicio de tu sesión.
.PARAMETER Desinstalar
    Quita TrafficBar, el acceso directo y el inicio automático.
.PARAMETER BorrarDatos
    Con -Desinstalar: también borra tu configuración e historial (%LOCALAPPDATA%\TrafficBar).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\Instalar-TrafficBar.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\Instalar-TrafficBar.ps1 -InicioConWindows
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\Instalar-TrafficBar.ps1 -Desinstalar
#>
[CmdletBinding()]
param(
    [string]$Origen = (Join-Path $PSScriptRoot "dist\TrafficBar"),
    [switch]$InicioConWindows,
    [switch]$Desinstalar,
    [switch]$BorrarDatos
)
$ErrorActionPreference = "Stop"

$destino = Join-Path $env:ProgramFiles "TrafficBar"
$acceso  = Join-Path ([Environment]::GetFolderPath("CommonPrograms")) "TrafficBar.lnk"
$runKey  = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$datos   = Join-Path $env:LOCALAPPDATA "TrafficBar"

# ---- 1) administrador
$yo = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $yo.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Se necesitan permisos de administrador. Aceptando el aviso de UAC continúa la instalación..."
    $a = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-Origen", "`"$Origen`"")
    if ($InicioConWindows) { $a += "-InicioConWindows" }
    if ($Desinstalar)      { $a += "-Desinstalar" }
    if ($BorrarDatos)      { $a += "-BorrarDatos" }
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $a
    return
}

function Detener-TrafficBar {
    Get-Process -Name TrafficBar -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Milliseconds 800
}

# ---- Desinstalar
if ($Desinstalar) {
    Detener-TrafficBar
    if (Test-Path -LiteralPath $destino) { Remove-Item -LiteralPath $destino -Recurse -Force }
    if (Test-Path -LiteralPath $acceso)  { Remove-Item -LiteralPath $acceso -Force }
    Remove-ItemProperty -Path $runKey -Name "TrafficBar" -ErrorAction SilentlyContinue
    if ($BorrarDatos -and (Test-Path -LiteralPath $datos)) { Remove-Item -LiteralPath $datos -Recurse -Force }
    Write-Host "TrafficBar desinstalado." -ForegroundColor Green
    if (-not $BorrarDatos) { Write-Host "Tu configuración e historial se conservaron en: $datos" }
    return
}

# ---- 2) copiar
$exeOrigen = Join-Path $Origen "TrafficBar.exe"
if (-not (Test-Path -LiteralPath $exeOrigen)) {
    throw "No encuentro TrafficBar.exe en '$Origen'. Compila primero (carpeta dist\TrafficBar) o usa -Origen."
}
Detener-TrafficBar
if (Test-Path -LiteralPath $destino) { Remove-Item -LiteralPath $destino -Recurse -Force }
Copy-Item -LiteralPath $Origen -Destination $destino -Recurse
Write-Host "Copiado a $destino"

# ---- 3) permisos: solo administradores pueden escribir
$acl = Get-Acl -LiteralPath $destino
$peligro = $acl.Access | Where-Object {
    $_.AccessControlType -eq "Allow" -and
    $_.IdentityReference.Value -match "(^|\\)(Users|Authenticated Users|Everyone|Usuarios|Usuarios autentificados|Todos)$" -and
    $_.FileSystemRights -match "Write|Modify|FullControl|CreateFiles|AppendData"
}
if ($peligro) {
    Write-Warning "El grupo de usuarios podía escribir en $destino. Se corrige."
    & icacls.exe $destino /inheritance:r /grant:r "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-545:(OI)(CI)RX" | Out-Null
}
Write-Host "Permisos de la carpeta instalada:"
& icacls.exe $destino | Select-Object -First 6

# ---- 4) acceso directo en el menú Inicio
$exe = Join-Path $destino "TrafficBar.exe"
$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut($acceso)
$lnk.TargetPath = $exe
$lnk.WorkingDirectory = $destino
$lnk.Description = "TrafficBar: barra de utilidades de navegación y red"
$lnk.Save()
Write-Host "Acceso directo creado en el menú Inicio."

# ---- 5) inicio con Windows (opcional, solo para tu usuario)
if ($InicioConWindows) {
    Set-ItemProperty -Path $runKey -Name "TrafficBar" -Value "`"$exe`" --segundo-plano"
    Write-Host "TrafficBar arrancará al iniciar tu sesión (en la bandeja del sistema)."
}

$hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
Write-Host ""
Write-Host "Instalación terminada." -ForegroundColor Green
Write-Host "SHA-256 de TrafficBar.exe: $hash"
Write-Host "(Guárdalo: si algún día cambia sin que hayas actualizado, algo modificó el programa.)"
Write-Host "Ábrelo desde el menú Inicio → TrafficBar."

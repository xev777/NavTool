<#
.SYNOPSIS
    Compila NavTool y genera el instalador y la versión portable (carpeta Output).
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\compilar.ps1
#>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 0) Plantilla de traducción (todos los textos de la app) y comprobación de que los packs son válidos
python extraer_textos.py
if ($LASTEXITCODE -ne 0) { throw "extraer_textos.py falló" }
python -c "import i18n,glob,sys; bad=[f for f in glob.glob('idiomas/*.json') if not f.endswith('plantilla.json') and not i18n.leer_pack(f)[0]]; sys.exit(1 if bad else 0)"
if ($LASTEXITCODE -ne 0) { throw "Hay un pack de idioma inválido en .\idiomas" }

# 1) NavTool en modo carpeta (no un .exe único: ver SEGURIDAD.md, hallazgo S3)
# Antes de cerrar NavTool a la fuerza, se le pide a Windows que recupere su proxy (si el ⏻ estaba encendido, un cierre
# brusco dejaría el proxy del sistema apuntando a un puerto muerto y programas como IDM dejarían de conectar).
python navtool.py --restaurar-proxy
Get-Process NavTool -ErrorAction SilentlyContinue | Stop-Process -Force
if (Test-Path "$PSScriptRoot\dist") { Remove-Item "$PSScriptRoot\dist" -Recurse -Force }
python -m PyInstaller --noconfirm --onedir --noconsole --name NavTool --icon navtool.ico `
    --add-data "navtool.ico;." --add-data "idiomas;idiomas" --add-data "creditos.json;." `
    --hidden-import traffic_monitor --hidden-import loadtrack --hidden-import load_panel `
    --hidden-import privacy --hidden-import report_view --hidden-import history `
    --hidden-import history_view --hidden-import watcher --hidden-import tray `
    --hidden-import proxy_core --hidden-import safety --hidden-import tooltip `
    --hidden-import ayuda --hidden-import i18n --hidden-import cuota --hidden-import programas `
    --hidden-import blocklists --hidden-import pcap --hidden-import netparse --hidden-import tienda `
    --hidden-import psutil navtool.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falló" }

# 2) Instalador con Inno Setup (inglés por defecto, con opción de español)
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
          "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "No encuentro Inno Setup 6 (winget install JRSoftware.InnoSetup)" }
& $iscc "$PSScriptRoot\NavTool.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup falló" }

$setup = Get-ChildItem "$PSScriptRoot\Output\NavTool-Setup-*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1

# 3) Versión portable: la misma carpeta + «portable.flag» (los datos van en la carpeta «Datos» de al lado)
$version = ([regex]::Match((Get-Content "$PSScriptRoot\NavTool.iss" -Raw), '#define AppVersion "([^"]+)"')).Groups[1].Value
$stage = "$PSScriptRoot\Output\_portable\NavTool"
if (Test-Path "$PSScriptRoot\Output\_portable") { Remove-Item "$PSScriptRoot\Output\_portable" -Recurse -Force }
New-Item -ItemType Directory $stage -Force | Out-Null
Copy-Item "$PSScriptRoot\dist\NavTool\*" $stage -Recurse
Set-Content "$stage\portable.flag" "Portable mode: NavTool keeps its settings and history in the 'Datos' folder next to it."
@"
NavTool $version - portable version / versión portable
======================================================

ENGLISH
-------
No installation needed:
  1. If Windows blocks the .zip, before extracting: right-click > Properties > check "Unblock".
  2. Extract the NavTool folder anywhere (disk, USB drive...).
  3. Run NavTool.exe.
Language: English by default. Change it any time: right-click the bar > "Idioma / Language".
Everything of yours (settings, history, block list) is stored in the "Datos" folder next to the program.
To take it with you, copy the whole folder. To erase your traces, delete "Datos".
It writes nothing to the registry or your profile ("Start with Windows" is not included).
The traffic monitor needs Npcap (npcap.com) and administrator rights. To quit: right-click the tray
icon > "Quit NavTool". The data in "Datos" includes the sites you visit: do not leave it on a USB you lend.

ESPAÑOL
-------
No necesita instalación:
  1. Si Windows bloquea el .zip, antes de extraerlo: clic derecho > Propiedades > marca "Desbloquear".
  2. Extrae la carpeta NavTool donde quieras (disco, memoria USB...).
  3. Ejecuta NavTool.exe.
Idioma: inglés por defecto. Cámbialo cuando quieras: clic derecho en la barra > "Idioma / Language".
Todo lo tuyo (configuración, historial, lista de bloqueo) se guarda en la carpeta "Datos" de al lado.
Para llevártelo, copia la carpeta entera. Para borrar tus huellas, borra "Datos".
No escribe nada en el registro ni en tu perfil: no incluye "Iniciar con Windows".
El monitor de tráfico necesita Npcap (npcap.com) y permisos de administrador. Como administrador
conviene ejecutar NavTool desde una carpeta que solo tú puedas modificar (ver SEGURIDAD.md, S3).
Para salir: clic derecho en el icono de la bandeja > "Salir de NavTool".
Los datos de "Datos" incluyen los sitios que visitas: no la dejes en un USB que prestes.
"@ | Set-Content "$stage\README.txt" -Encoding UTF8
$zip = "$PSScriptRoot\Output\NavTool-Portable-$version.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $stage -DestinationPath $zip -CompressionLevel Optimal
Remove-Item "$PSScriptRoot\Output\_portable" -Recurse -Force

Write-Host ""
Write-Host "Installer : $($setup.FullName)  ($([math]::Round($setup.Length/1MB,1)) MB)" -ForegroundColor Green
Write-Host "   SHA-256 : $((Get-FileHash $setup.FullName -Algorithm SHA256).Hash)"
Write-Host "Portable   : $zip  ($([math]::Round((Get-Item $zip).Length/1MB,1)) MB)" -ForegroundColor Green
Write-Host "   SHA-256 : $((Get-FileHash $zip -Algorithm SHA256).Hash)"

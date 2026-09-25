; TrafficBar installer (Inno Setup 6).  Build:  ISCC.exe TrafficBar.iss   ->   Output\TrafficBar-Setup-1.0.exe
; Instalador de TrafficBar. Antes hay que generar dist\TrafficBar con PyInstaller (ver compilar.ps1).
; Este archivo se guarda en UTF-8 CON BOM para que los textos con tildes se vean bien.
;
; Idioma: el asistente se abre en INGLÉS y ofrece elegir ESPAÑOL. La elección se guarda en
; {app}\idioma.txt y es el idioma inicial de la aplicación (luego se cambia desde la propia barra).

#define AppName "TrafficBar"
#define AppVersion "2.0.0"
#define AppExe "TrafficBar.exe"

[Setup]
AppId={{FA9D2CBD-4691-4E3A-AE9C-AB39DD6B2DE1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Fernando Erazo
AppPublisherURL=https://github.com/xev777/TrafficBar
AppSupportURL=https://github.com/xev777/TrafficBar/issues
VersionInfoVersion={#AppVersion}.0
VersionInfoCompany=Fernando Erazo
VersionInfoProductName=TrafficBar
VersionInfoDescription=TrafficBar installer
VersionInfoCopyright=Copyright (C) 2026 Fernando Erazo. GNU GPL v3.
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Program Files: only an administrator can modify the installed files (see SEGURIDAD.md, S3)
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=TrafficBar-Setup-{#AppVersion}
SetupIconFile=trafficbar.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
; Always ask the language, and start in English (do not follow the Windows language)
ShowLanguageDialog=yes
LanguageDetectionMethod=none

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
english.TaskDesktop=Create a desktop shortcut
spanish.TaskDesktop=Crear un acceso directo en el escritorio
english.TaskAutostart=Start TrafficBar with Windows (stays in the system tray)
spanish.TaskAutostart=Iniciar TrafficBar con Windows (queda en la bandeja del sistema)
english.RunNow=Open TrafficBar now
spanish.RunNow=Abrir TrafficBar ahora
english.NpcapNote=TrafficBar is installed.%n%nTo use the traffic monitor ("Traffic") you also need Npcap (npcap.com). The rest of the features do not need it.
spanish.NpcapNote=TrafficBar está instalado.%n%nPara usar el monitor de tráfico ("Tráfico") necesitas además Npcap (npcap.com). El resto de funciones no lo necesita.
english.DeleteData=Do you also want to delete your TrafficBar settings and history?%n%n
spanish.DeleteData=¿Quieres borrar también tu configuración y tu historial de TrafficBar?%n%n

[Tasks]
Name: "desktopicon"; Description: "{cm:TaskDesktop}"; Flags: unchecked
Name: "autostart"; Description: "{cm:TaskAutostart}"; Flags: unchecked

[Files]
Source: "dist\TrafficBar\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; Start with Windows is registered by the app itself with YOUR user (not the administrator account that
; elevates the installer): HKCU only, no extra permissions, removed on uninstall.
Filename: "{app}\{#AppExe}"; Parameters: "--activar-inicio"; Flags: runhidden runasoriginaluser waituntilterminated; Tasks: autostart
Filename: "{app}\{#AppExe}"; Description: "{cm:RunNow}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{app}\{#AppExe}"; Parameters: "--desactivar-inicio"; Flags: runhidden; RunOnceId: "QuitarInicio"
; Removes the Windows Firewall rules TrafficBar created ("TrafficBar block: ...")
Filename: "{app}\{#AppExe}"; Parameters: "--quitar-bloqueos"; Flags: runhidden waituntilterminated; RunOnceId: "QuitarBloqueos"
; Removes the Microsoft Store apps loopback exemptions TrafficBar created
Filename: "{app}\{#AppExe}"; Parameters: "--quitar-exenciones"; Flags: runhidden waituntilterminated; RunOnceId: "QuitarExenciones"

[UninstallDelete]
Type: files; Name: "{app}\idioma.txt"

[Code]
// Closes TrafficBar before installing/updating/uninstalling. First it asks TrafficBar to give Windows back its
// proxy setting (otherwise an abrupt close could leave you without Internet).
procedure DetenerTrafficBar(const Carpeta: String);
var
  Codigo: Integer;
begin
  if FileExists(Carpeta + '\{#AppExe}') then
    Exec(Carpeta + '\{#AppExe}', '--restaurar-proxy', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Sleep(800);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  DetenerTrafficBar(ExpandConstant('{app}'));
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  DetenerTrafficBar(ExpandConstant('{app}'));
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Codigo: String;
begin
  if CurStep = ssPostInstall then
  begin
    // App language chosen in the wizard (the user can change it later from the bar)
    if ActiveLanguage = 'spanish' then Codigo := 'es' else Codigo := 'en';
    SaveStringToFile(ExpandConstant('{app}\idioma.txt'), Codigo, False);
    if (not DirExists(ExpandConstant('{sys}\Npcap'))) and (not WizardSilent) then
      MsgBox(CustomMessage('NpcapNote'), mbInformation, MB_OK);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Datos: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Datos := ExpandConstant('{localappdata}\{#AppName}');
    // In a silent uninstall it NEVER asks or deletes anything of yours
    if (not UninstallSilent()) and DirExists(Datos) and
       (MsgBox(CustomMessage('DeleteData') + Datos, mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
      DelTree(Datos, True, True, True);
  end;
end;

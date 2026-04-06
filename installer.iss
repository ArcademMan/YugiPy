; YugiPy Inno Setup Script
; Requires Inno Setup 6+ (https://jrsoftware.org/isinfo.php)

#define MyAppName "YugiPy"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "ArcademMan"
#define MyAppExeName "YugiPy.exe"
#define MyAppURL "https://github.com/riccardo/yugipy"

[Setup]
AppId={{B8A3F2E1-4D5C-4E6F-A7B8-9C0D1E2F3A4B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=YugiPy-Setup-{#MyAppVersion}
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

; Dark wizard appearance
WizardImageFile=assets\icon.png
WizardSmallImageFile=assets\icon.png

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startmenu"; Description: "Create a Start Menu shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; PyInstaller output directory
Source: "dist\YugiPy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Pre-built card hash index + CLIP model — placed in APPDATA so the app works out of the box
Source: "dist\YugiPy\_internal\data\card_hashes.db"; DestDir: "{userappdata}\AmMstools\YugiPy\data"; Flags: onlyifdoesntexist
Source: "dist\YugiPy\_internal\data\clip_visual.onnx"; DestDir: "{userappdata}\AmMstools\YugiPy\data"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenu
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; Tasks: startmenu
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Option to launch after install
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up generated certs in install dir
Type: filesandordirs; Name: "{app}\certs"

[Code]
// Add Windows Firewall rule for port 8000 during install
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    Exec('netsh', 'advfirewall firewall add rule name="YugiPy Server" dir=in action=allow protocol=TCP localport=8000', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

// Remove firewall rule on uninstall
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Exec('netsh', 'advfirewall firewall delete rule name="YugiPy Server"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

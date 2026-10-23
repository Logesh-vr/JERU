#define AppVersion "0.1.1"

[Setup]
AppId={{AE019910-6C11-4E2B-AD3D-7907B3F59C4C}
AppName=Jeru
AppVersion={#AppVersion}
AppPublisher=Jeru
DefaultDirName={localappdata}\Programs\Jeru
DefaultGroupName=Jeru
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\releases
OutputBaseFilename=Jeru-Setup-{#AppVersion}
SetupIconFile=..\assets\jeru.ico
Compression=lzma2/fast
SolidCompression=no
WizardStyle=modern
UninstallDisplayIcon={app}\Jeru.exe
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\Jeru\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Jeru"; Filename: "{app}\Jeru.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Jeru"; Filename: "{app}\Jeru.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Jeru.exe"; Description: "Open Jeru"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{userstartup}\Jeru voice assistant.lnk"

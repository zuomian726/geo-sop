#ifndef MyAppVersion
#define MyAppVersion "0.3.12-dev"
#endif

#define MyAppName "GEO-SOP"
#define MyAppPublisher "GEO-SOP"
#define MyAppExe "Install GEO-SOP.bat"

[Setup]
AppId={{49B60D46-D22F-45D4-8F05-GEOSOP001}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\GEO-SOP
DefaultGroupName=GEO-SOP
DisableProgramGroupPage=yes
OutputDir=..\..\release
OutputBaseFilename=GEO-SOP-Setup-v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".git\*,.github\*,.venv*\*,web_app\venv\*,build\*,dist\*,release\*,browser_profile\*,answers\*,*.db,*.dmg,*.zip,*.exe"

[Icons]
Name: "{group}\GEO-SOP"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\GEO-SOP"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; Description: "Launch GEO-SOP"; Flags: postinstall skipifsilent shellexec

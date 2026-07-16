#ifndef MyAppVersion
#define MyAppVersion "0.3.44-dev"
#endif

#define MyAppName "GEO-SOP"
#define MyAppPublisher "GEO-SOP"
#define MyAppExe "GEO-SOP.exe"

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
UninstallDisplayIcon={app}\{#MyAppExe}
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\dist\GEO-SOP\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\.playwright-browsers\*"; DestDir: "{app}\ms-playwright"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\GEO-SOP"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\GEO-SOP"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\geo-sop"; ValueType: string; ValueName: ""; ValueData: "URL:GEO-SOP Protocol"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\geo-sop"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\geo-sop\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExe}"" ""%1"""

[Run]
Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; Description: "Launch GEO-SOP"; Flags: postinstall skipifsilent nowait

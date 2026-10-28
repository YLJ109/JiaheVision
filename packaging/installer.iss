#define AppName "家和视觉"
#define AppVersion "1.0.0"
#define Root ".."

[Setup]
AppId={{108D21D7-D90E-4D48-BAF1-A8A48AA5DCA1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=家和
MinVersion=10.0
DefaultDirName={localappdata}\Programs\JiaheVision
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#Root}\output
OutputBaseFilename=家和视觉-Setup
SetupIconFile={#Root}\assets\logo.ico
UninstallDisplayIcon={app}\JiaheVision.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "{#Root}\dist\JiaheVision\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: unchecked

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\JiaheVision.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\JiaheVision.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\JiaheVision.exe"; Description: "启动家和视觉"; Flags: nowait postinstall skipifsilent

#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif
#ifndef AppId
  #define AppId "{C839D095-61F1-42C5-B15A-019522A52C51}"
#endif

[Setup]
AppId={{#AppId}
AppName=AST Manager
AppVersion={#AppVersion}
AppPublisher=AST
AppPublisherURL=https://github.com/manueltuescher/AST-Manager
DefaultDirName={localappdata}\Programs\AST-Manager
DefaultGroupName=AST Manager
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\installer-output
OutputBaseFilename=AST-Verwaltung-Setup-x64
SetupIconFile=..\assets\ast.ico
UninstallDisplayIcon={app}\AST-Verwaltung.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
CloseApplicationsFilter=AST-Verwaltung.exe,*.dll,*.pyd
RestartApplications=no
UsePreviousAppDir=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Files]
Source: "..\dist\AST-Verwaltung\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AST Manager"; Filename: "{app}\AST-Verwaltung.exe"
Name: "{group}\AST Manager Demo"; Filename: "{app}\AST-Verwaltung.exe"; Parameters: "--demo"

[Run]
Filename: "{app}\AST-Verwaltung.exe"; Description: "AST Manager starten"; Flags: nowait postinstall skipifsilent; Check: NotUpdate
Filename: "{app}\AST-Verwaltung.exe"; Parameters: "{code:UpdateParameters}"; Flags: nowait runasoriginaluser; Check: IsUpdate

[Code]
function IsUpdate: Boolean;
begin
  Result := ExpandConstant('{param:ASTUPDATE|0}') = '1';
end;

function NotUpdate: Boolean;
begin
  Result := not IsUpdate;
end;

function UpdateParameters(Param: String): String;
var DataDir: String;
begin
  Result := '';
  DataDir := ExpandConstant('{param:ASTDATADIR|}');
  if DataDir <> '' then
    Result := '--data-dir ' + AddQuotes(DataDir);
  if ExpandConstant('{param:ASTDEMO|0}') = '1' then
    Result := Result + ' --demo';
end;

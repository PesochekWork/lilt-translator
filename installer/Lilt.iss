; Build through build-installer.ps1 so the version and package are checked first.
#ifndef AppVersion
  #error Pass AppVersion from lilt/__init__.py with /DAppVersion.
#endif
#ifndef PackageDir
  #define PackageDir "..\dist\Lilt"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\installer"
#endif

[Setup]
; Keep this ID unchanged so later releases update the same installation.
AppId={{98C621BD-92CF-43B5-AA2D-C1853B41A03E}
AppName=Lilt
AppVersion={#AppVersion}
AppPublisher=PesochekWork
AppPublisherURL=https://github.com/PesochekWork/lilt-translator
AppSupportURL=https://github.com/PesochekWork/lilt-translator/issues
AppUpdatesURL=https://github.com/PesochekWork/lilt-translator/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Lilt
DefaultGroupName=Lilt
AllowNoIcons=yes
PrivilegesRequired=lowest
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=setup
SetupIconFile=..\tools\lilt.ico
UninstallDisplayIcon={app}\Lilt.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
; The complete PyInstaller folder includes Qt, Python, docs and license notices.
Source: "{#PackageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Lilt"; Filename: "{app}\Lilt.exe"; WorkingDir: "{app}"; IconFilename: "{app}\Lilt.exe"
Name: "{userdesktop}\Lilt"; Filename: "{app}\Lilt.exe"; WorkingDir: "{app}"; IconFilename: "{app}\Lilt.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Lilt.exe"; Description: "Open Lilt"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

; No UninstallDelete entries: user history, cards, preferences and credentials
; in {localappdata}\Lilt belong to the user and survive uninstalling the app.

[Code]
function IsCurrentInstallationStartupCommand(const Command: String): Boolean;
var
  Executable, Candidate: String;
begin
  Executable := Lowercase(ExpandConstant('{app}\Lilt.exe'));
  Candidate := Lowercase(Trim(Command));
  { The app uses list2cmdline: executable paths containing spaces are quoted.
    Match the whole command, not a path substring, so an alternate portable
    copy or a command with different arguments keeps its startup registration. }
  Result := (Candidate = Executable + ' --startup') or
    (Candidate = '"' + Executable + '" --startup');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  RegisteredCommand: String;
begin
  if CurUninstallStep <> usUninstall then
    Exit;
  { Preferences creates startup registration only after the user opts in.
    Remove only this installation's value for the current Windows account;
    never delete the shared Run key or anything from the user's data folder. }
  if RegQueryStringValue(HKEY_CURRENT_USER,
    'Software\Microsoft\Windows\CurrentVersion\Run', 'Lilt', RegisteredCommand) then
    if IsCurrentInstallationStartupCommand(RegisteredCommand) then
      RegDeleteValue(HKEY_CURRENT_USER,
        'Software\Microsoft\Windows\CurrentVersion\Run', 'Lilt');
end;

{ Inno Setup 6 runs a 32-bit setup process, including when installing an x64
  application. Its Pascal engine uses Integer for these Win32 pointer/handles. }
function OpenExistingFileForWrite(const FileName: String; DesiredAccess,
  ShareMode: Cardinal; SecurityAttributes: Integer; CreationDisposition,
  FlagsAndAttributes: Cardinal; TemplateFile: Integer): Integer;
  external 'CreateFileW@kernel32.dll stdcall';

function CloseFileHandle(Handle: Integer): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function FindUnavailableBinary(const Directory: String): String;
var
  Entry: TFindRec;
  FileName, Extension: String;
  Handle: Integer;
begin
  Result := '';
  if not FindFirst(AddBackslash(Directory) + '*', Entry) then
    Exit;
  try
    repeat
      if (Entry.Name <> '.') and (Entry.Name <> '..') then
      begin
        FileName := AddBackslash(Directory) + Entry.Name;
        if (Entry.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
        begin
          { Do not follow directory links outside the installation. }
          if (Entry.Attributes and $400) = 0 then
            Result := FindUnavailableBinary(FileName);
        end
        else
        begin
          Extension := Lowercase(ExtractFileExt(FileName));
          if (Extension = '.exe') or (Extension = '.dll') or
             (Extension = '.pyd') then
          begin
            { OPEN_EXISTING with no writes performed. Loaded Windows image
              files reject write access; allow every sharing mode otherwise. }
            Handle := OpenExistingFileForWrite(FileName, $40000000, 7, 0,
              3, $80, 0);
            if Handle = -1 then
              Result := FileName
            else
              CloseFileHandle(Handle);
          end;
        end;
        if Result <> '' then
          Exit;
      end;
    until not FindNext(Entry);
  finally
    FindClose(Entry);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  UnavailableFile: String;
begin
  Result := '';
  UnavailableFile := FindUnavailableBinary(ExpandConstant('{app}'));
  if UnavailableFile <> '' then
    Result := 'A Lilt application file is in use or cannot be updated.' + #13#10 +
      'Save any text you need, choose Quit Lilt from its system-tray menu, ' +
      'and try again. Setup will not close the app for you.' + #13#10#13#10 +
      UnavailableFile;
end;

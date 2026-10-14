#ifndef BundleDir
  #define BundleDir "..\dist\DocumentAssistant"
#endif
#ifndef OutputDirPath
  #define OutputDirPath "..\dist"
#endif
[Setup]
AppId={{34F0E85B-EC8D-4D95-B87B-70D7B3F994B2}
AppName=DocumentAssistant
AppVersion=0.22.0
AppPublisher=ZLongLab
AppPublisherURL=https://github.com/ZLongLab/DocumentAssistant
DefaultDirName={code:DefaultInstallDir}
DefaultGroupName=DocumentAssistant
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDirPath}
OutputBaseFilename=DocumentAssistant-0.22.0-Windows-x64-Setup
SetupIconFile=..\document_assistant\documentassistant.ico
UninstallDisplayIcon={app}\DocumentAssistant.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
DisableDirPage=no
UninstallDisplayName=DocumentAssistant

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"; GroupDescription: "{cm:ShortcutGroup}"; Flags: checkedonce

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DocumentAssistant"; Filename: "{app}\DocumentAssistant.exe"; AppUserModelID: "DocumentAssistant.Workbench"
Name: "{userdesktop}\DocumentAssistant"; Filename: "{app}\DocumentAssistant.exe"; Tasks: desktopicon; AppUserModelID: "DocumentAssistant.Workbench"

[Run]
Filename: "{app}\DocumentAssistant.exe"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[CustomMessages]
chinesesimp.DesktopShortcut=创建桌面快捷方式
chinesesimp.ShortcutGroup=快捷方式：
chinesesimp.LaunchApp=启动 DocumentAssistant
english.DesktopShortcut=Create a desktop shortcut
english.ShortcutGroup=Shortcuts:
english.LaunchApp=Launch DocumentAssistant

[Code]
function DefaultInstallDir(Param: String): String;
begin
  if DirExists('D:\') then Result := 'D:\Apps\DocumentAssistant'
  else Result := ExpandConstant('{localappdata}\Programs\DocumentAssistant');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var Existing: String;
begin
  if CurUninstallStep = usUninstall then
    if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'DocumentAssistant', Existing) then
      if (Pos('"' + ExpandConstant('{app}\DocumentAssistant.exe') + '" --tray ', Existing) = 1) or
         (Pos(ExpandConstant('{app}\DocumentAssistant.exe') + ' --tray ', Existing) = 1) then
        RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'DocumentAssistant');
end;

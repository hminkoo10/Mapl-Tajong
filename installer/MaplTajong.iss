; 마고 타종 Windows 설치 파일 (Inno Setup 6)
; 빌드: python tools\build.py  (AppVersion/SourceDir/OutputDir 를 넘겨 준다)
;
; - 사용자 계정에만 설치(관리자 권한 필요 없음) → 자동 업데이트 때 UAC 창이 뜨지 않음
; - 시간표/종소리 데이터는 %APPDATA%\MaplTajong 에 있어 설치·업데이트·제거해도 그대로 남음

#define AppName "마고 타종"
#define AppExe "Mataf.exe"
#define AppGuid "A56AE072-9E6B-4E54-9FF5-8F92F05B34AB"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\Mataf"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\installer"
#endif
#ifndef SetupIcon
  #define SetupIcon "..\app\assets\ui\app.ico"
#endif

[Setup]
; AppId 는 절대 바꾸면 안 됨 (바꾸면 업데이트가 아니라 새 프로그램으로 설치됨)
AppId={{{#AppGuid}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=마고수학학원
AppPublisherURL=https://github.com/hminkoo10/Mapl-Tajong
AppUpdatesURL=https://github.com/hminkoo10/Mapl-Tajong/releases
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
DefaultDirName={autopf}\MaplTajong
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
UsePreviousAppDir=yes
UsePreviousTasks=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile={#SetupIcon}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputDir={#OutputDir}
OutputBaseFilename=MaplTajong-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
ShowLanguageDialog=no

[Languages]
#if FileExists(AddBackslash(CompilerPath) + "Languages\Korean.isl")
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
#else
Name: "english"; MessagesFile: "compiler:Default.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "바탕 화면에 바로가기 만들기"; GroupDescription: "추가 작업:"
Name: "autostart"; Description: "컴퓨터를 켜면 자동으로 실행"; GroupDescription: "추가 작업:"

[InstallDelete]
; 이전 버전의 라이브러리 폴더를 지우고 새로 깐다 (남은 파일 때문에 생기는 오류 방지)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; 처음 설치할 때만 자동 실행을 등록한다. 그 뒤로는 프로그램 설정에서 켜고 끈 값을 존중한다.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MaplTajong"; ValueData: """{app}\{#AppExe}"""; Tasks: autostart; Check: not IsUpgrade

[Run]
; 직접 설치했을 때: 마지막 화면의 '실행' 체크
Filename: "{app}\{#AppExe}"; Description: "마고 타종 실행"; Flags: nowait postinstall skipifsilent
; 자동 업데이트(조용한 설치)일 때: 설치가 끝나면 바로 다시 켠다
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM {#AppExe} /F"; Flags: runhidden; RunOnceId: "StopApp"

[Code]
function IsUpgrade(): Boolean;
begin
  Result := RegValueExists(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{' + '{#AppGuid}' + '}_is1', 'UninstallString');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'MaplTajong');
end;

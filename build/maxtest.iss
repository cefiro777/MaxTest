; Установщик MaxTest (Inno Setup 6).
;
; Собирается скриптом tools\build_release.py — он сначала пересобирает
; приложение через PyInstaller, потом запускает ISCC.exe для этого файла.
;
; Ключевые решения:
;   * PrivilegesRequired=lowest — установка идёт в профиль пользователя и НЕ
;     требует прав администратора. Если администратор запустит установщик от
;     своего имени, будет предложена установка для всех пользователей.
;   * Данные (результаты, тесты, журналы) живут в %APPDATA%\MaxTest и при
;     удалении программы сохраняются, если пользователь явно не согласится
;     их стереть. Годовая аттестация не должна пропасть из-за переустановки.

#define AppName "MaxTest"
#define AppVersion "1.0.0"
#define AppPublisher "MaxTest"
#define AppExe "MaxTest.exe"

[Setup]
; ВНИМАНИЕ: AppId менять нельзя — по нему Windows опознаёт установленную
; программу при обновлении и удалении.
AppId={{7C1B4E52-9E1F-4A5D-9C6B-2A6F0D3B1E44}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=ЛИЦЕНЗИЯ.txt
OutputDir=..\dist
OutputBaseFilename=MaxTest-Setup-{#AppVersion}
SetupIconFile=..\maxtest\resources\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} — аттестация сотрудников
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Сборка не подписана сертификатом — предупреждаем об этом в конце установки.
AppSupportURL=
AppUpdatesURL=

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"
Name: "startmenuicon"; Description: "Создать ярлык в меню «Пуск»"; GroupDescription: "Дополнительно:"; Flags: checkedonce

[Files]
Source: "..\dist\MaxTest\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\docs\АДМИНИСТРАТОРУ.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\СОТРУДНИКУ.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\samples\demo.qtest"; DestDir: "{app}\samples"; Flags: ignoreversion
Source: "ЛИЦЕНЗИЯ.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startmenuicon
Name: "{group}\Инструкция администратора"; Filename: "{app}\docs\АДМИНИСТРАТОРУ.md"; Tasks: startmenuicon
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"; Tasks: startmenuicon
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Файлы, созданные приложением рядом с программой (журналы аварий и т.п.).
Type: filesandordirs; Name: "{app}\_internal\__pycache__"
Type: dirifempty; Name: "{app}"

[Code]
var
  PinPage: TInputQueryWizardPage;
  PinAlreadySet: Boolean;

function DataDir(): String;
begin
  Result := ExpandConstant('{userappdata}\MaxTest');
end;

procedure InitializeWizard();
begin
  PinAlreadySet := FileExists(DataDir() + '\security.json');

  PinPage := CreateInputQueryPage(wpSelectTasks,
    'PIN-код администратора',
    'Защита разделов, которые сотруднику видеть не нужно',
    'PIN-код закрывает конструктор тестов, результаты, проверку ответов и ' +
    'справочник сотрудников. Раздел «Пройти тест» остаётся доступным всем.' + #13#10 + #13#10 +
    'Оставьте поля пустыми, если хотите задать код позже — это можно сделать ' +
    'в главном окне программы.' + #13#10 +
    'Внимание: забытый PIN-код восстановить нельзя.');

  PinPage.Add('PIN-код (не короче 4 символов):', True);
  PinPage.Add('Повторите PIN-код:', True);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  { Если код уже задан прошлой установкой — не предлагаем задать его снова. }
  if (PageID = PinPage.ID) and PinAlreadySet then
    Result := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = PinPage.ID then
  begin
    if (PinPage.Values[0] = '') and (PinPage.Values[1] = '') then
      Exit;  { пропуск установки PIN — допустимый выбор }

    if Length(PinPage.Values[0]) < 4 then
    begin
      SuppressibleMsgBox('PIN-код должен быть не короче 4 символов.', mbError, MB_OK, IDOK);
      Result := False;
      Exit;
    end;

    if PinPage.Values[0] <> PinPage.Values[1] then
    begin
      SuppressibleMsgBox('Введённые коды не совпадают.', mbError, MB_OK, IDOK);
      Result := False;
      Exit;
    end;
  end;
end;

procedure ApplyPin();
var
  PinFile: String;
  ResultCode: Integer;
begin
  if PinAlreadySet or (PinPage.Values[0] = '') then
    Exit;

  { PIN передаётся файлом, а не аргументом командной строки: аргументы видны
    в диспетчере задач. Программа читает файл и сразу его удаляет. }
  PinFile := ExpandConstant('{tmp}\maxtest_pin.txt');
  if not SaveStringToFile(PinFile, PinPage.Values[0], False) then
  begin
    SuppressibleMsgBox('Не удалось передать PIN-код программе. Задайте его ' +
           'вручную в главном окне MaxTest.', mbError, MB_OK, IDOK);
    Exit;
  end;

  if not Exec(ExpandConstant('{app}\{#AppExe}'), '--set-pin-file "' + PinFile + '"',
              '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
    SuppressibleMsgBox('Не удалось установить PIN-код. Задайте его вручную ' +
           'в главном окне MaxTest (кнопка «Задать PIN»).', mbError, MB_OK, IDOK);

  DeleteFile(PinFile);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    ApplyPin();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Answer: Integer;
begin
  if CurUninstallStep <> usUninstall then
    Exit;

  if not DirExists(DataDir()) then
    Exit;

  { SuppressibleMsgBox, а не MsgBox: обычный MsgBox из [Code] НЕ подчиняется
    ключу /SUPPRESSMSGBOXES, и тихое удаление (в том числе через «Приложения и
    возможности» в корпоративном развёртывании) зависало бы на невидимом
    диалоге. Последний аргумент — ответ по умолчанию в тихом режиме.
    По умолчанию — НЕТ: результаты аттестаций за прошлые годы дороже, чем
    оставшаяся папка. }
  Answer := SuppressibleMsgBox(
    'Удалить также данные MaxTest?' + #13#10 + #13#10 +
    'Будут безвозвратно удалены результаты аттестаций, файлы тестов, ' +
    'резервные копии базы, журналы и PIN-код из папки:' + #13#10 +
    DataDir() + #13#10 + #13#10 +
    'Нажмите «Нет», чтобы сохранить данные для будущей установки.',
    mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO);

  if Answer = IDYES then
    DelTree(DataDir(), True, True, True);
end;

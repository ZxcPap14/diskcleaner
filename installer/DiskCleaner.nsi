; DiskCleaner Pro — установщик NSIS 3.x
; Сборка: python build_installer.py
; Прямая компиляция:
;   makensis /DAPP_VERSION=4.10.1 /DSOURCE_DIR=..\dist /DOUTPUT_FILE=..\dist\Setup.exe installer\DiskCleaner.nsi

Unicode true
SetCompressor /SOLID lzma
SetCompressorDictSize 32
CRCCheck on
XPStyle on
ManifestDPIAware true
RequestExecutionLevel user

!include "MUI2.nsh"

!ifndef APP_VERSION
  !define APP_VERSION "4.10.1"
!endif
!ifndef SOURCE_DIR
  !define SOURCE_DIR "..\dist"
!endif
!ifndef PROJECT_DIR
  !define PROJECT_DIR ".."
!endif
!ifndef OUTPUT_FILE
  !define OUTPUT_FILE "..\dist\DiskCleaner-Setup-${APP_VERSION}.exe"
!endif

!define APP_NAME "DiskCleaner Pro"
!define APP_EXE "DiskCleaner.exe"
!define APP_PUBLISHER "ZCode"
!define APP_REG_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\DiskCleanerPro"

Name "${APP_NAME}"
OutFile "${OUTPUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\DiskCleaner Pro"
InstallDirRegKey HKCU "${APP_REG_KEY}" "InstallLocation"
BrandingText "${APP_NAME} ${APP_VERSION} · ${APP_PUBLISHER}"
ShowInstDetails show
ShowUninstDetails show
AutoCloseWindow false

VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "CompanyName" "${APP_PUBLISHER}"
VIAddVersionKey "FileDescription" "Установщик ${APP_NAME}"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"
VIAddVersionKey "LegalCopyright" "MIT License"

; ── Оформление ────────────────────────────────────────
!define MUI_ICON "${PROJECT_DIR}\assets\diskcleaner.ico"
!define MUI_UNICON "${PROJECT_DIR}\assets\diskcleaner.ico"
Icon "${PROJECT_DIR}\assets\diskcleaner.ico"
UninstallIcon "${PROJECT_DIR}\assets\diskcleaner.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEFINISHPAGE_BITMAP "${PROJECT_DIR}\assets\installer_welcome.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "${PROJECT_DIR}\assets\installer_welcome.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "${PROJECT_DIR}\assets\installer_header.bmp"
!define MUI_HEADERIMAGE_RIGHT

!define MUI_WELCOMEPAGE_TITLE "Установка ${APP_NAME}"
!define MUI_WELCOMEPAGE_TEXT "Мастер установит ${APP_NAME} ${APP_VERSION} в папку вашего профиля.$\r$\n$\r$\nОчистка диска, SMART-диагностика и проверка поверхности — всё в одном приложении.$\r$\n$\r$\nНажмите «Далее», чтобы продолжить."

!define MUI_FINISHPAGE_TITLE "Установка завершена"
!define MUI_FINISHPAGE_TEXT "${APP_NAME} ${APP_VERSION} установлен.$\r$\n$\r$\nЯрлыки добавлены в меню «Пуск» и, если выбрано, на рабочий стол."
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Запустить ${APP_NAME}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${PROJECT_DIR}\LICENSE"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Russian"

; ── Установка ─────────────────────────────────────────
Section "${APP_NAME}" SEC_MAIN
  SectionIn RO
  SetShellVarContext current

  SetOutPath "$INSTDIR"
  File /oname=${APP_EXE} "${SOURCE_DIR}\${APP_EXE}"
  File /oname=README.md "${PROJECT_DIR}\README.md"
  File /oname=LICENSE "${PROJECT_DIR}\LICENSE"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
    "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\Удалить ${APP_NAME}.lnk" \
    "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "${APP_REG_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "${APP_REG_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "${APP_REG_KEY}" "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKCU "${APP_REG_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE},0"
  WriteRegStr HKCU "${APP_REG_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${APP_REG_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${APP_REG_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${APP_REG_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${APP_REG_KEY}" "NoRepair" 1
  WriteRegDWORD HKCU "${APP_REG_KEY}" "EstimatedSize" 32000

  DetailPrint "Установлено в $INSTDIR"
SectionEnd

Section "Ярлык на рабочем столе" SEC_DESKTOP
  SetShellVarContext current
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" \
    "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_MAIN} \
    "Основные файлы ${APP_NAME}, ярлыки в меню «Пуск» и деинсталлятор."
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESKTOP} \
    "Добавить ярлык ${APP_NAME} на рабочий стол."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ── Инициализация ─────────────────────────────────────
Function .onInit
  SetShellVarContext current
  SetRegView 64
FunctionEnd

Function un.onInit
  SetShellVarContext current
  SetRegView 64
FunctionEnd

; ── Удаление ──────────────────────────────────────────
Section "Uninstall"
  SetShellVarContext current

  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\Удалить ${APP_NAME}.lnk"
  RMDir "$SMPROGRAMS\${APP_NAME}"

  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  DeleteRegKey HKCU "${APP_REG_KEY}"

  IfSilent skip_data
  MessageBox MB_YESNO|MB_ICONQUESTION \
    "Удалить настройки, историю очисток и логи ${APP_NAME}?" \
    IDNO skip_data
  RMDir /r "$APPDATA\DiskCleaner"

skip_data:
SectionEnd

@REM @echo off
@REM rem Auto install PymiereLink extension to Premiere on windows

@REM echo Downloading Adobe Extension Manager
@REM curl "http://download.macromedia.com/pub/extensionmanager/ExManCmd_win.zip" --output %temp%\ExManCmd_win.zip
@REM echo.

@REM echo Download PymiereLink extension
@REM curl "https://raw.githubusercontent.com/qmasingarbe/pymiere/master/pymiere_link.zxp" --output %temp%\pymiere_link.zxp
@REM echo.

echo Unzip Extension Manager
rem require powershell
powershell Expand-Archive %temp%\ExManCmd_win.zip -DestinationPath %temp%\ExManCmd_win -Force
echo.

echo Install Extension
call %temp%\ExManCmd_win\ExManCmd.exe /install %temp%\pymiere_link.zxp
if %ERRORLEVEL% NEQ 0 (
    echo Installation failed...
) else (
    echo.
    echo Installation successful !
)

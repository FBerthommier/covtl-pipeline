@echo off
rem ============================================================
rem  vtl-synth quick launch (Windows)
rem  Edit the SCRIPTS path below to match your Python install,
rem  or add it once to your user PATH and call vtl-synth directly.
rem ============================================================
setlocal

set SCRIPTS=%APPDATA%\Python\Python39\Scripts
set PATH=%SCRIPTS%;%PATH%

vtl-synth run "this is easy for us" -o out

echo.
pause
endlocal

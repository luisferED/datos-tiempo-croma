@echo off
set "URL=http://127.0.0.1:6667"
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if exist "%EDGE%" (
  start "" "%EDGE%" --explicitly-allowed-ports=6667 --app=%URL%
  exit /b
)
set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if exist "%EDGE%" (
  start "" "%EDGE%" --explicitly-allowed-ports=6667 --app=%URL%
  exit /b
)
where msedge.exe >nul 2>nul
if not errorlevel 1 (
  start "" msedge.exe --explicitly-allowed-ports=6667 --app=%URL%
  exit /b
)
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME%" (
  start "" "%CHROME%" --explicitly-allowed-ports=6667 --app=%URL%
  exit /b
)
set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME%" (
  start "" "%CHROME%" --explicitly-allowed-ports=6667 --app=%URL%
  exit /b
)
where chrome.exe >nul 2>nul
if not errorlevel 1 (
  start "" chrome.exe --explicitly-allowed-ports=6667 --app=%URL%
  exit /b
)
echo No se encontro Edge o Chrome en PATH.
echo Abra el navegador con --explicitly-allowed-ports=6667 y visite %URL%
pause

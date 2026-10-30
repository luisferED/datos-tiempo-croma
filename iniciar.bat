@echo off
cd /d "%~dp0"
python app.py
if errorlevel 1 (
  echo.
  echo La aplicacion termino con un error.
  echo Si es la primera vez, ejecute instalar.bat.
  pause
)

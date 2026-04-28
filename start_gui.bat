@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo [ERROR] Not found: .venv\Scripts\activate.bat
  echo Please create virtual environment and install requirements first.
  echo See README.md -> Installation.
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
python -m src.gui_app

if errorlevel 1 (
  echo.
  echo [ERROR] GUI launch failed. Please check messages above.
)
pause

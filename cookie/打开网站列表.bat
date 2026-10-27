@echo off
rem Double-click to open the site login manager list window
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw main.py & exit /b)
where python >nul 2>nul && (start "" python main.py & exit /b)
echo Python not found. Please install Python 3 first.
pause

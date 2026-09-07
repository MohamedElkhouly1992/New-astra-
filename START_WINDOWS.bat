@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 app.py
goto finish
:try_python
python app.py
:finish
if errorlevel 1 (
echo Install Python 3 with Tcl/Tk, then run this file again.
pause
)

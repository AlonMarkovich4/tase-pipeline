@echo off
:: TASE Pipeline -- runs at system startup as a background process
:: The pipeline handles its own schedule (Mon-Fri 09:30-17:30)

set SCRIPT_DIR=%~dp0
set TASK_NAME=TASE_Pipeline

:: Find pythonw.exe (runs without a console window)
for /f "delims=" %%i in ('where pythonw.exe 2^>nul') do set PYTHONW=%%i
if "%PYTHONW%"=="" (
    echo pythonw.exe not found, falling back to python.exe
    for /f "delims=" %%i in ('where python.exe 2^>nul') do set PYTHONW=%%i
)

echo.
echo  TASE Pipeline Setup
echo  ====================
echo  Python : %PYTHONW%
echo  Script : %SCRIPT_DIR%main.py
echo  Task   : %TASK_NAME%
echo.

:: Create task that runs at logon (background, no window)
schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%PYTHONW%\" \"%SCRIPT_DIR%main.py\"" ^
  /sc onlogon ^
  /f ^
  /rl highest

if %errorlevel% == 0 (
    echo.
    echo  Task created successfully!
    echo  The pipeline will start automatically when you log in.
    echo  It runs Mon-Fri 09:30-17:30 every 15 minutes.
    echo.
    echo  To start now  : schtasks /run /tn "%TASK_NAME%"
    echo  To check      : schtasks /query /tn "%TASK_NAME%"
    echo  To stop       : schtasks /end /tn "%TASK_NAME%"
    echo  To remove     : schtasks /delete /tn "%TASK_NAME%" /f
    echo.

    :: Start it right now too
    echo Starting pipeline now...
    schtasks /run /tn "%TASK_NAME%"
) else (
    echo.
    echo  ERROR: Could not create task.
    echo  Right-click setup_task.bat ^> "Run as administrator"
)

pause

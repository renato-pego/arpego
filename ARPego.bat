@echo off
cd /d "%~dp0"

where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw app_windows.py
    exit
)

where python >nul 2>&1
if %errorlevel% equ 0 (
    start "" python app_windows.py
    exit
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    start "" py app_windows.py
    exit
)

echo Python nao encontrado no sistema.
pause

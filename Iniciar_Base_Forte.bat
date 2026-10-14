@echo off
title ARPego - Base Forte Desktop (SQL Server)
cls
echo ====================================================================
echo  Iniciando ARPego - Base Forte Windows Desktop (SQL Server ASSISTPE)
echo ====================================================================
echo.
cd /d "%~dp0"
python app_windows.py
if errorlevel 1 (
    echo.
    echo [AVISO] Ocorreu um erro na execucao. Verifique o Python e pyodbc.
    pause
)

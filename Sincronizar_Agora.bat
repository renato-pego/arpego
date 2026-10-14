@echo off
title ARPego - Sincronizacao com a Nuvem
cls
echo ====================================================================
echo  Sincronizando Base Forte (SQL Server) com a Nuvem (Render)...
echo ====================================================================
echo.
cd /d "%~dp0"
python app_windows.py --sync
echo.
echo ====================================================================
echo  Sincronizacao finalizada! Janela fechara em 5 segundos...
echo ====================================================================
timeout /t 5 >nul

@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ======================================================
echo   ARPego - Restaurando Tarefa de Manutencao do Carro
echo ======================================================
echo.
python restaurar_tarefa.py
echo.
echo ======================================================
echo   Processo finalizado.
echo ======================================================
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ======================================================
echo   [1/2] Restaurando Tarefa do Carro e Sincronizando...
echo ======================================================
python restaurar_tarefa.py
echo.
echo ======================================================
echo   [2/2] Realizando Commit e Push para o GitHub...
echo ======================================================
git config --global --add safe.directory "%CD:\=/%"
git config --global --add safe.directory "%CD%"
git add .
git commit -m "fix: anti-sobrescrita em sync, envio de projetos, atalho desktop unico e pwa standalone"
git push -u origin main --force
echo.
echo ======================================================
echo   Tudo concluido com sucesso!
echo ======================================================

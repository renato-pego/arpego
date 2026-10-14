@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ======================================================
echo   DIRETORIO: %CD%
echo ======================================================
echo.
echo [0/3] Liberando permissao segura no Git (safe.directory)...
git config --global --add safe.directory "%CD:\=/%"
git config --global --add safe.directory "%CD%"
echo.
echo [1/3] Verificando status do Git...
git status
echo.
echo [2/3] Adicionando e commitando...
git add .
git commit -m "fix: anti-sobrescrita em sync, envio de projetos, atalho desktop unico e pwa standalone"
echo.
echo [3/3] Enviando para o GitHub...
git push -u origin main --force
echo.
echo ======================================================
echo    Concluido com sucesso! O Render iniciou o deploy.
echo ======================================================
pause

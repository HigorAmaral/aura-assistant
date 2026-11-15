@echo off
setlocal enabledelayedexpansion
title Instalador Oficial AURA OS (Auto-Update via main)

set "REPO_OWNER=HigorAmaral"
set "REPO_NAME=aura-assistant"
set "BRANCH=main"
set "INSTALL_DIR=%LOCALAPPDATA%\AURA-OS"

echo ============================================================
echo   AURA OS - Instalador Automatico com Auto-Update (main)
echo   Repositorio: %REPO_OWNER%/%REPO_NAME%
echo   Destino:     %INSTALL_DIR%
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python 3.10+ nao encontrado no PATH.
    echo Instale o Python em https://www.python.org/downloads/ marcando "Add Python to PATH".
    pause
    exit /b 1
)

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

where git >nul 2>&1
if not errorlevel 1 (
    if exist "%INSTALL_DIR%\.git" (
        echo [1/4] Atualizando repositorio existente na branch %BRANCH%...
        pushd "%INSTALL_DIR%"
        git fetch origin %BRANCH%
        git reset --hard origin/%BRANCH%
        popd
    ) else (
        echo [1/4] Clonando repositorio %REPO_OWNER%/%REPO_NAME% (%BRANCH%)...
        git clone --branch %BRANCH% "https://github.com/%REPO_OWNER%/%REPO_NAME%.git" "%INSTALL_DIR%"
    )
) else (
    echo [1/4] Git nao encontrado. Baixando pacote ZIP da branch %BRANCH%...
    set "ZIP_TMP=%TEMP%\aura-main.zip"
    set "EXT_TMP=%TEMP%\aura-extract"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://github.com/%REPO_OWNER%/%REPO_NAME%/archive/refs/heads/%BRANCH%.zip' -OutFile '%ZIP_TMP%'"
    if exist "%EXT_TMP%" rmdir /s /q "%EXT_TMP%"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%ZIP_TMP%' -DestinationPath '%EXT_TMP%' -Force"
    for /d %%D in ("%EXT_TMP%\*") do (
        xcopy "%%D\*" "%INSTALL_DIR%\" /E /Y /I >nul
    )
    del /q "%ZIP_TMP%" >nul 2>&1
    rmdir /s /q "%EXT_TMP%" >nul 2>&1
)

echo [2/4] Instalando dependencias Python...
python -m pip install --upgrade pip --quiet
python -m pip install -r "%INSTALL_DIR%\requirements.txt" pywebview pystray pillow --quiet

echo [3/4] Criando atalho AURA OS na Area de Trabalho...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\AURA OS.lnk'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%INSTALL_DIR%\Iniciar_AURA_Background.vbs\"'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Description = 'AURA OS - Assistente de Computador'; $s.Save()"

echo [4/4] Iniciando AURA OS em segundo plano...
start "" wscript.exe "%INSTALL_DIR%\Iniciar_AURA_Background.vbs"

echo.
echo [CONCLUIDO] AURA OS instalada e iniciada!
echo Sempre que houver um novo commit na branch '%BRANCH%', o app atualizara sozinho.
timeout /t 4 >nul
exit /b 0

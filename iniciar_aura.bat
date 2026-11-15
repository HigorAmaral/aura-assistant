@echo off
title AURA - Assistente de Computador (Modo Barra no Topo)
cd /d "%~dp0"
echo Iniciando AURA em segundo plano no centro superior da tela...
start "" pythonw.exe "%~dp0desktop_widget.py"
exit

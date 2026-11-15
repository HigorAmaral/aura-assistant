#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "========================================================"
echo "  AURA OS 3.0 — Edicao Ubuntu Linux & Multi-Agentes"
echo "========================================================"

if ! command -v python3 &> /dev/null; then
    echo "Instalando Python3..."
    sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-tk xdg-utils
fi

python3 -m pip install --user -r requirements.txt --quiet || python3 -m pip install --break-system-packages -r requirements.txt --quiet

echo "Iniciando AURA OS em segundo plano (Barra no Topo + Servidor LAN :8765)..."
nohup python3 desktop_widget.py >/dev/null 2>&1 &
echo "AURA OS ativa! Pressione Ctrl+Shift+A ou acesse http://localhost:8765"

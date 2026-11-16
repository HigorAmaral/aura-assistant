#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "========================================================"
echo "  AURA OS 5.0 — Edicao Ubuntu Linux & Multi-Agentes"
echo "========================================================"

if ! command -v python3 &> /dev/null; then
    echo "Instalando Python3 e dependencias do sistema..."
    sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv python3-tk xdg-utils
fi

if [ ! -d ".venv" ]; then
    echo "Criando ambiente virtual (.venv)..."
    if ! python3 -m venv .venv 2>/dev/null; then
        echo "Instalando python3-venv e python3-tk..."
        sudo apt-get update && sudo apt-get install -y python3-venv python3-tk xdg-utils
        python3 -m venv .venv
    fi
fi

echo "Instalando/atualizando dependencias Python no .venv..."
.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet

echo "Iniciando AURA OS em segundo plano (Servidor :8765)..."
nohup .venv/bin/python desktop_widget.py >/tmp/aura-os.log 2>&1 &
AURA_PID=$!
sleep 2

if kill -0 "$AURA_PID" 2>/dev/null; then
    echo "AURA OS ativa (PID $AURA_PID)! Acesse http://localhost:8765"
    echo "Logs em: /tmp/aura-os.log"
else
    echo "Falha ao iniciar AURA OS. Veja os logs abaixo:"
    tail -n 30 /tmp/aura-os.log || true
    exit 1
fi

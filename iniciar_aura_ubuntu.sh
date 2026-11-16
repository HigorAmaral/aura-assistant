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

if [ ! -x ".venv/bin/pip" ]; then
    echo "Configurando ambiente virtual (.venv)..."
    rm -rf .venv
    if ! python3 -m venv .venv 2>/dev/null; then
        echo "Instalando python3-venv e python3-tk..."
        sudo apt-get update && sudo apt-get install -y python3-venv python3-tk xdg-utils
        rm -rf .venv
        python3 -m venv .venv
    fi
fi

echo "Instalando/atualizando dependencias Python no .venv..."
.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt

echo "Iniciando AURA OS em segundo plano (Servidor :8765)..."
nohup .venv/bin/python desktop_widget.py >/tmp/aura-os.log 2>&1 &
AURA_PID=$!

READY=0
for _ in $(seq 1 30); do
    if .venv/bin/python -c "import socket; s=socket.socket(); s.settimeout(0.3); exit(0 if s.connect_ex(('127.0.0.1', 8765))==0 else 1)" 2>/dev/null; then
        READY=1
        break
    fi
    if ! kill -0 "$AURA_PID" 2>/dev/null; then
        break
    fi
    sleep 0.5
done

if [ "$READY" -eq 1 ]; then
    echo "AURA OS ativa (PID $AURA_PID)! Acesse: http://localhost:8765"
    echo "Logs em: /tmp/aura-os.log"
    if command -v xdg-open &> /dev/null; then
        xdg-open "http://localhost:8765" >/dev/null 2>&1 &
    fi
else
    echo "Falha ao iniciar AURA OS. Veja os logs abaixo:"
    cat /tmp/aura-os.log || true
    exit 1
fi

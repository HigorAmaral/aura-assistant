# AURA OS — Assistente Pessoal de Computador com IA

Assistente inteligente de computador pessoal para **Windows e Linux (Ubuntu)** com **controle total do sistema**, **Central IA & PC em tempo real**, **terminal integrado**, **otimizador de desempenho**, **barra HUD flutuante no topo da tela**, **acesso remoto via celular (4G/5G e Wi-Fi)**, **automações em segundo plano** e **auto-update automático pela branch `main`**.

---

## Principais Recursos

- **Central IA & PC (Painel Principal)** (`static/index.html`, `ai_engine.py`, `system_tools.py`):
  - Chat inteligente com suporte a **comandos em linguagem natural** (abrir/fechar programas, tirar prints, limpar arquivos temporários, diagnosticar rede, gerenciar processos, volume/mídia e modos Dev/Estudo).
  - Monitoramento ao vivo de **CPU, Memória RAM, Disco, Rede e Uptime**.
  - **Ações Rápidas de 1 Clique** (Print da Tela, Limpar Temp, Otimizar RAM, Flush DNS, Volume, Mídia) e **Terminal Rápido do Sistema** embutido.
- **Controle Total do Sistema (Windows & Linux)** (`system_tools.py`, `file_tools.py`):
  - Abertura e fechamento de aplicativos (com fallback automático de elevação UAC no Windows quando necessário), sincronização de apps instalados, diagnóstico de rede, monitoramento de hardware e limpeza de arquivos temporários.
- **Otimizador do PC & Manutenção** (`system_optimizer.py`):
  - Limpeza de caches e temporários, otimização de RAM, flush de DNS, análise de arquivos grandes e inicialização do sistema.
- **Barra HUD Flutuante no Topo da Tela** (`desktop_widget.py`, `static/hud.html`):
  - Fica posicionada no centro superior da tela (quando executada em ambiente desktop), com atalho global `Ctrl+Shift+A`, ícone na bandeja do sistema (`pystray`) e acesso rápido ao chat/terminal.
- **Múltiplos Provedores de IA & Memória Persistente** (`free_ai_router.py`, `memory_engine.py`, `storage.py`):
  - Suporte a Pool Gratuito, Google Gemini, Groq, OpenRouter e Ollama local, com banco SQLite (`aura_data.db`) para histórico de conversas, memória evolutiva, tarefas, notas, clipboard inteligente e logs.
- **Acesso Remoto Mobile 4G/5G + Notificações Push** (`remote_bridge.py`, `static/mobile.html`):
  - Túnel público / Cloud Relay para controlar o computador pelo celular mesmo fora da mesma rede Wi-Fi, com proteção por PIN e notificações automáticas.
- **Automações, Clipboard Inteligente & Pomodoro** (`automation_engine.py`):
  - Regras agendadas (intervalo, horário diário ou alerta de CPU/RAM), histórico inteligente de `Ctrl+C` e timer Pomodoro integrado.
- **App Instalável & Auto-Update Automático (`main`)** (`updater.py`, `Instalar_AURA.bat`, `.github/workflows/release-app.yml`):
  - Sempre que um novo commit é enviado para a branch `main`, o aplicativo instalado detecta a atualização automaticamente, baixa o código atualizado, atualiza dependências se necessário e reinicia com a nova versão.

---

## Instalação Rápida (Windows)

### Opção 1 — Instalador Automático (Recomendado)
1. Baixe o arquivo [`Instalar_AURA.bat`](https://github.com/HigorAmaral/aura-assistant/releases/latest/download/Instalar_AURA.bat) (ou diretamente do repositório).
2. Execute com duplo clique.
3. O instalador irá:
   - Instalar a AURA OS em `%LOCALAPPDATA%\AURA-OS` (via `git clone` na branch `main` ou download automático do ZIP da `main`);
   - Instalar as dependências Python (`requirements.txt`, `pywebview`, `pystray`, `pillow`);
   - Criar o atalho **AURA OS** na Área de Trabalho;
   - Iniciar a AURA OS em segundo plano.

### Opção 2 — Execução Manual / Desenvolvimento
```bash
git clone https://github.com/HigorAmaral/aura-assistant.git
cd aura-assistant
pip install -r requirements.txt pywebview pystray pillow
python desktop_widget.py
```
Ou no Windows, execute diretamente `iniciar_aura.bat` / `Iniciar_AURA_Background.vbs`.

---

## Instalação Rápida (Linux / Ubuntu)

> **Nota:** O arquivo `Instalar_AURA.bat` é exclusivo para **Windows**. No Linux/Ubuntu, utilize o script [`iniciar_aura_ubuntu.sh`](iniciar_aura_ubuntu.sh), que cria automaticamente o ambiente virtual `.venv` (compatível com Ubuntu 24.04 / PEP 668), instala as dependências e inicia o servidor em `http://localhost:8765`.

### 1. Primeira instalação (comando pronto em 1 passo)
```bash
git clone https://github.com/HigorAmaral/aura-assistant.git && cd aura-assistant && chmod +x iniciar_aura_ubuntu.sh && ./iniciar_aura_ubuntu.sh
```

### 2. Se já tiver a pasta `aura-assistant` (atualizar e iniciar)
```bash
cd aura-assistant && git pull origin main && chmod +x iniciar_aura_ubuntu.sh && ./iniciar_aura_ubuntu.sh
```

> **Painel Web Local:** `http://localhost:8765`  
> **Painel Mobile:** `http://localhost:8765/mobile`  
> **Logs em segundo plano (Linux):** `tail -f /tmp/aura-os.log`

---

## Como Funciona o Auto-Update pela Branch `main`

1. Você faz alterações no projeto e envia um commit para a branch `main`:
   ```bash
   git add .
   git commit -m "sua melhoria"
   git push origin main
   ```
2. O GitHub Actions (`.github/workflows/release-app.yml`) gera automaticamente os artefatos atualizados (`AURA-OS-Portable.zip` e `Instalar_AURA.bat`) na release `latest`.
3. O daemon de atualização em segundo plano (`updater.py`) no app instalado verifica periodicamente a branch `main` (configurável na aba **Configurações**):
   - Se instalado via Git: executa `git fetch origin main` + `git reset --hard origin/main`.
   - Se instalado via pacote portátil (sem Git): consulta a API de commits da `main`, baixa o novo pacote, preserva `aura_data.db` e `.env`, atualiza o código e reinicia o app automaticamente.

---

## Estrutura do Projeto

| Arquivo / Pasta | Função |
| --- | --- |
| `desktop_widget.py` | Inicializa o servidor FastAPI, barra HUD no topo, tray icon e atalho `Ctrl+Shift+A` |
| `app.py` | API REST FastAPI (`localhost:8765`), rotas do chat, sistema, otimizador e auto-update |
| `updater.py` | Motor de verificação, aplicação de updates da `main` e reinício automático |
| `ai_engine.py` | Orquestração de respostas do assistente e execução de ações no computador |
| `free_ai_router.py` | Roteamento inteligente entre modelos gratuitos e provedores configurados |
| `system_tools.py` | Controle do SO, apps instalados, elevação UAC, hardware, rede e rotinas |
| `system_optimizer.py` | Limpeza de temporários, otimização de RAM, DNS e manutenção do sistema |
| `terminal_manager.py` | Sessões de terminal integrado (PowerShell/Bash) no painel |
| `remote_bridge.py` | Cloud Relay e túnel público para acesso remoto pelo celular |
| `automation_engine.py` | Automações agendadas, monitor de clipboard e Pomodoro |
| `storage.py` | Persistência SQLite (`aura_data.db`) para configurações, chat, tarefas e notas |
| `static/` | Interfaces web: `index.html` (Central IA & PC), `hud.html` (Barra Topo) e `mobile.html` |
| `iniciar_aura_ubuntu.sh` | Instalador/inicializador automático para Linux / Ubuntu com `.venv` |
| `Instalar_AURA.bat` | Instalador automático Windows com criação de atalho |
| `build_exe.py` | Script PyInstaller para gerar executável Windows (`AURA-OS.exe`) |
| `.github/workflows/release-app.yml` | Pipeline CI/CD para publicar builds automáticos a cada push na `main` |

---

## Build de Executável (`.exe`) Opcional

Caso deseje gerar um executável standalone no Windows:
```bash
pip install pyinstaller
python build_exe.py
```
O resultado será gerado em `dist/AURA-OS/`.

# AURA OS 5.0 — Ultimate Maestri & Automation Suite

Assistente de computador pessoal com **controle total do sistema**, **Quadro Maestri 2D** (orquestração visual de agentes com terminal embutido), **barra HUD flutuante no topo da tela**, **acesso remoto via celular (4G/5G e rede local)**, **automações em segundo plano** e **sistema de instalação com auto-update automático pela branch `main`**.

---

## Principais Recursos

- **Barra HUD Flutuante (Top-Center WebView2)** (`desktop_widget.py`, `static/hud.html`):
  - Fica posicionada no centro superior da tela, com atalho global `Ctrl+Shift+A` e ícone na bandeja do sistema (`pystray`).
  - Terminal/prompt rápido integrado e acesso com 1 clique ao painel completo.
- **Quadro Maestri 2D & Multi-Agentes** (`static/index.html`, `ai_engine.py`, `terminal_manager.py`):
  - Canvas interativo com blocos conectáveis, minimapa, execução direta no terminal do agente (modo Híbrido: prompts em português + comandos PowerShell/Bash) e visualização em tempo real do trabalho dos agentes.
- **Controle Total do Sistema Windows / Linux** (`system_tools.py`, `file_tools.py`):
  - Abertura e fechamento de aplicativos (incluindo fallback automático de elevação UAC via `ShellExecuteW` para apps como o Gerenciador de Tarefas), sincronização automática de apps instalados no PC, diagnóstico de rede, monitoramento de CPU/RAM/Disco em tempo real, limpeza de arquivos temporários, controle de volume/mídia e rotinas rápidas.
- **Múltiplos Provedores de IA & Memória Persistente** (`free_ai_router.py`, `memory_engine.py`, `storage.py`):
  - Suporte a Pool Gratuito, Google Gemini, Groq, OpenRouter e Ollama local, com banco SQLite (`aura_data.db`) para memória, tarefas, notas, clipboard inteligente e logs.
- **Acesso Remoto Mobile 4G/5G + Notificações Push** (`remote_bridge.py`, `static/mobile.html`):
  - Túnel público / Cloud Relay para controlar o PC pelo celular mesmo fora da mesma rede Wi-Fi, além de notificações automáticas quando tarefas do Maestri, terminal ou atualizações terminam.
- **Automações, Clipboard Inteligente & Pomodoro** (`automation_engine.py`):
  - Regras agendadas (intervalo, horário diário ou alerta de CPU/RAM), histórico inteligente de `Ctrl+C` e timer Pomodoro.
- **App Instalável & Auto-Update Automático (`main`)** (`updater.py`, `Instalar_AURA.bat`, `.github/workflows/release-app.yml`):
  - Sempre que um novo commit é enviado para a branch `main`, o aplicativo instalado detecta a atualização automaticamente, baixa o código atualizado (via Git ou pacote ZIP da `main`), atualiza dependências se necessário, envia notificação e reinicia com a nova versão.

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
3. O daemon de atualização em segundo plano (`updater.py`) no app instalado verifica periodicamente a branch `main` (padrão a cada `60s`, configurável na **Aba 7 — Configurações do Sistema**):
   - Se instalado via Git: executa `git fetch origin main` + `git reset --hard origin/main`.
   - Se instalado via pacote portátil (sem Git): consulta a API de commits da `main`, baixa o novo pacote, preserva `aura_data.db` e `.env`, atualiza o código e reinicia o app automaticamente.

---

## Estrutura do Projeto

| Arquivo / Pasta | Função |
| --- | --- |
| `desktop_widget.py` | Inicializa o servidor FastAPI, barra HUD CSS3 no topo, tray icon e atalho `Ctrl+Shift+A` |
| `app.py` | API REST FastAPI (`localhost:8765`), rotas do chat, Maestri, sistema e auto-update |
| `updater.py` | Motor de verificação, aplicação de updates da `main`, reinício automático e gerador de `.zip` |
| `ai_engine.py` | Orquestração de respostas, chat principal e execução de agentes no Quadro Maestri 2D |
| `free_ai_router.py` | Roteamento inteligente entre modelos gratuitos e provedores configurados |
| `system_tools.py` | Controle do SO, apps instalados, elevação UAC, hardware, rede e rotinas |
| `terminal_manager.py` | Sessões de terminal híbrido (IA + PowerShell/Bash) para os agentes |
| `remote_bridge.py` | Cloud Relay e túnel público para acesso remoto pelo celular |
| `automation_engine.py` | Automações agendadas, monitor de clipboard e Pomodoro |
| `storage.py` | Persistência SQLite (`aura_data.db`) para configurações, tarefas, notas e estado |
| `static/` | Interfaces web: `index.html` (Painel/Maestri), `hud.html` (Barra Topo) e `mobile.html` |
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

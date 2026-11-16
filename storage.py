import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = Path(__file__).parent / "aura_data.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT DEFAULT 'Geral',
                priority TEXT DEFAULT 'media',
                due_time TEXT DEFAULT '',
                done INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                fact TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                source TEXT DEFAULT 'auto',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS custom_triggers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phrase TEXT NOT NULL UNIQUE,
                action_command TEXT NOT NULL,
                times_used INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS habit_stats (
                action_key TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0,
                last_used TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS canvas_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                nodes_json TEXT NOT NULL,
                edges_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS automations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                schedule_type TEXT NOT NULL,
                schedule_value TEXT NOT NULL,
                action_type TEXT NOT NULL,
                action_payload TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                last_run TEXT DEFAULT 'Nunca',
                last_result TEXT DEFAULT '',
                run_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS clipboard_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'Texto',
                pinned INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS synced_apps (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                target_path TEXT NOT NULL,
                exe_name TEXT DEFAULT '',
                category TEXT DEFAULT 'Aplicativos',
                icon TEXT DEFAULT 'app-window',
                source TEXT DEFAULT 'auto',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                provider TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            """
        )

        # Seed default welcome tasks if empty
        if conn.execute("SELECT COUNT(*) as cnt FROM tasks").fetchone()["cnt"] == 0:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute(
                "INSERT INTO tasks (title, category, priority, due_time, done, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("Explorar o Quadro Infinito Maestri 2D com múltiplos agentes", "Agentes IA", "alta", "Hoje", 0, now),
            )
            conn.execute(
                "INSERT INTO tasks (title, category, priority, due_time, done, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("Conectar celular via QR Code na aba Mobile Connect", "Conectividade", "media", "Hoje", 0, now),
            )

        # Seed default memories if empty
        if conn.execute("SELECT COUNT(*) as cnt FROM memories").fetchone()["cnt"] == 0:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute(
                "INSERT INTO memories (category, fact, confidence, source, created_at) VALUES (?, ?, ?, ?, ?)",
                ("Preferência", "O usuário prefere respostas diretas e objetivas em Português do Brasil.", 1.0, "sistema", now),
            )
            conn.execute(
                "INSERT INTO memories (category, fact, confidence, source, created_at) VALUES (?, ?, ?, ?, ?)",
                ("Ambiente", "O usuário utiliza automação multi-agente estilo Maestri e barra superior em segundo plano.", 1.0, "sistema", now),
            )

        # Seed default custom trigger if empty
        if conn.execute("SELECT COUNT(*) as cnt FROM custom_triggers").fetchone()["cnt"] == 0:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute(
                "INSERT INTO custom_triggers (phrase, action_command, times_used, created_at) VALUES (?, ?, ?, ?)",
                ("hora de codar", "Ative o modo dev", 1, now),
            )
            conn.execute(
                "INSERT INTO custom_triggers (phrase, action_command, times_used, created_at) VALUES (?, ?, ?, ?)",
                ("limpar tudo", "Ative o modo faxina", 1, now),
            )

        # Seed default automations if empty
        if conn.execute("SELECT COUNT(*) as cnt FROM automations").fetchone()["cnt"] == 0:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute(
                """
                INSERT INTO automations (name, schedule_type, schedule_value, action_type, action_payload, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Sentinela de Hardware (Alerta RAM/CPU)",
                    "threshold",
                    "88",
                    "system_alert",
                    "Verificar se uso de CPU ou RAM ultrapassou 88% e alertar no celular",
                    1,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO automations (name, schedule_type, schedule_value, action_type, action_payload, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Limpeza Automática de Temporários",
                    "interval",
                    "120",
                    "routine",
                    "modo_faxina",
                    0,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO automations (name, schedule_type, schedule_value, action_type, action_payload, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Relatório Diário de Produtividade IA",
                    "daily",
                    "18:00",
                    "ai_prompt",
                    "Faça um resumo motivador das minhas tarefas pendentes e do status do meu PC.",
                    1,
                    now,
                ),
            )

        # Seed default Maestri 2D Canvas nodes & edges if empty
        if conn.execute("SELECT COUNT(*) as cnt FROM canvas_state").fetchone()["cnt"] == 0:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            tpl = get_maestri_templates()["default"]
            conn.execute(
                "INSERT INTO canvas_state (id, nodes_json, edges_json, updated_at) VALUES (1, ?, ?, ?)",
                (
                    json.dumps(tpl["nodes"], ensure_ascii=False),
                    json.dumps(tpl["edges"], ensure_ascii=False),
                    now,
                ),
            )


def get_maestri_templates() -> Dict[str, Dict[str, Any]]:
    """Pre-built multi-agent + live terminal Maestri 2D templates."""
    return {
        "default": {
            "name": "Orquestração Geral & Sistema",
            "description": "4 agentes conectados com terminal ao vivo para produtividade, pesquisa e telemetria.",
            "nodes": [
                {
                    "id": "agent-maestro",
                    "name": "Maestro Orquestrador",
                    "role": "Coordena o objetivo geral e sintetiza o trabalho dos agentes conectados.",
                    "model": "free:openai",
                    "x": 70,
                    "y": 90,
                    "prompt": "Planeje uma rotina de alta produtividade e delegue subtarefas técnicas e de pesquisa.",
                    "terminal_cmd": "python --version",
                    "view_mode": "split",
                    "output": "Pronto para orquestrar os agentes no canvas.",
                    "status": "idle",
                    "color": "#38bdf8",
                },
                {
                    "id": "agent-researcher",
                    "name": "Agente Pesquisador Web",
                    "role": "Busca dados em tempo real na internet e resume tendências.",
                    "model": "free:mistral",
                    "x": 510,
                    "y": 40,
                    "prompt": "Pesquise e resuma as principais tendências de agentes autônomos de IA.",
                    "terminal_cmd": "",
                    "view_mode": "split",
                    "output": "Aguardando execução do fluxo ou comando individual.",
                    "status": "idle",
                    "color": "#818cf8",
                },
                {
                    "id": "agent-sysops",
                    "name": "Agente Engenheiro PC (Win/Ubuntu)",
                    "role": "Analisa telemetria do sistema, processos, arquivos e automações locais.",
                    "model": "free:qwen-coder",
                    "x": 510,
                    "y": 380,
                    "prompt": "Analise o status atual de CPU e Memória RAM do computador e recomende otimizações.",
                    "terminal_cmd": "whoami",
                    "view_mode": "split",
                    "output": "Aguardando execução do fluxo ou comando individual.",
                    "status": "idle",
                    "color": "#34d399",
                },
                {
                    "id": "agent-memory",
                    "name": "Agente Estrategista & Memória",
                    "role": "Consulta a memória evolutiva do usuário e gera plano de ação e tarefas.",
                    "model": "free:deepseek",
                    "x": 960,
                    "y": 200,
                    "prompt": "Com base nas descobertas anteriores e na memória do usuário, crie 3 ações práticas.",
                    "terminal_cmd": "",
                    "view_mode": "split",
                    "output": "Aguardando contexto dos agentes anteriores.",
                    "status": "idle",
                    "color": "#c084fc",
                },
            ],
            "edges": [
                {"from": "agent-maestro", "to": "agent-researcher"},
                {"from": "agent-maestro", "to": "agent-sysops"},
                {"from": "agent-researcher", "to": "agent-memory"},
                {"from": "agent-sysops", "to": "agent-memory"},
            ],
        },
        "software_factory": {
            "name": "Fábrica de Software Full-Stack",
            "description": "Arquiteto de Sistema -> Dev Backend + Dev Frontend -> QA & Testes no Terminal.",
            "nodes": [
                {
                    "id": "node-arch",
                    "name": "Arquiteto de Software",
                    "role": "Define arquitetura limpa, contratos de API REST e estrutura de banco de dados.",
                    "model": "free:openai",
                    "x": 70,
                    "y": 160,
                    "prompt": "Defina a arquitetura enxuta de um microsserviço em Python FastAPI + SQLite com autenticação.",
                    "terminal_cmd": "python --version",
                    "view_mode": "split",
                    "output": "Pronto para projetar a arquitetura.",
                    "status": "idle",
                    "color": "#38bdf8",
                },
                {
                    "id": "node-backend",
                    "name": "Engenheiro Backend & API",
                    "role": "Implementa endpoints, regras de negócio, SQL e segurança.",
                    "model": "free:qwen-coder",
                    "x": 510,
                    "y": 40,
                    "prompt": "Com base na arquitetura recebida, escreva o código dos endpoints principais e modelos Pydantic.",
                    "terminal_cmd": "pip --version",
                    "view_mode": "split",
                    "output": "Aguardando especificação do Arquiteto.",
                    "status": "idle",
                    "color": "#34d399",
                },
                {
                    "id": "node-frontend",
                    "name": "Especialista UI/UX & CSS",
                    "role": "Cria interfaces modernas, responsivas e componentes interativos.",
                    "model": "free:mistral",
                    "x": 510,
                    "y": 380,
                    "prompt": "Projete os componentes visuais e chamadas fetch() para consumir a API definida pelo Arquiteto.",
                    "terminal_cmd": "",
                    "view_mode": "split",
                    "output": "Aguardando especificação do Arquiteto.",
                    "status": "idle",
                    "color": "#818cf8",
                },
                {
                    "id": "node-qa",
                    "name": "Engenheiro QA & DevSecOps",
                    "role": "Revisa código, identifica bugs/vulnerabilidades e valida testes no terminal.",
                    "model": "free:deepseek",
                    "x": 960,
                    "y": 200,
                    "prompt": "Revise o Backend e Frontend gerados, aponte melhorias de segurança e liste o checklist de deploy.",
                    "terminal_cmd": "git --version",
                    "view_mode": "split",
                    "output": "Aguardando entregas de Backend e Frontend.",
                    "status": "idle",
                    "color": "#fbbf24",
                },
            ],
            "edges": [
                {"from": "node-arch", "to": "node-backend"},
                {"from": "node-arch", "to": "node-frontend"},
                {"from": "node-backend", "to": "node-qa"},
                {"from": "node-frontend", "to": "node-qa"},
            ],
        },
        "coding_squad": {
            "name": "Squad Full-Stack Pro (Maestro + DB + Back + Front + QA)",
            "description": "Maestro Comandante coordena Banco de Dados, Backend API, Frontend UI/UX e QA com testes reais.",
            "nodes": [
                {
                    "id": "squad-maestro",
                    "name": "Maestro Comandante (Tech Lead)",
                    "role": "Comanda o squad de código: define arquitetura, contratos de API, delega para DB/Back/Front e sintetiza.",
                    "model": "free:deepseek",
                    "x": 60,
                    "y": 210,
                    "prompt": "Coordene o desenvolvimento completo, definindo arquitetura, contratos de dados e delegando para DB, Backend, Frontend e QA.",
                    "terminal_cmd": "git status",
                    "view_mode": "split",
                    "output": "Comandante pronto para orquestrar o Squad de Código.",
                    "status": "idle",
                    "color": "#38bdf8",
                },
                {
                    "id": "squad-db",
                    "name": "Arquiteto Banco de Dados (SQL)",
                    "role": "Modela tabelas SQLite/PostgreSQL, relacionamentos, índices, migrations e queries otimizadas.",
                    "model": "free:qwen-coder",
                    "x": 540,
                    "y": 40,
                    "prompt": "Projete o schema de banco de dados (tabelas, chaves, índices) e crie/valide os arquivos SQL ou models.",
                    "terminal_cmd": "",
                    "view_mode": "split",
                    "output": "Aguardando diretriz do Maestro Comandante.",
                    "status": "idle",
                    "color": "#fbbf24",
                },
                {
                    "id": "squad-backend",
                    "name": "Engenheiro Backend (API)",
                    "role": "Implementa APIs REST/FastAPI/Node, validação Pydantic, autenticação e integração com o Banco de Dados.",
                    "model": "free:qwen-coder",
                    "x": 540,
                    "y": 380,
                    "prompt": "Implemente as rotas da API consumindo o schema do Banco de Dados e expondo endpoints limpos para o Frontend.",
                    "terminal_cmd": "python3 --version",
                    "view_mode": "split",
                    "output": "Aguardando schema do Banco de Dados.",
                    "status": "idle",
                    "color": "#34d399",
                },
                {
                    "id": "squad-frontend",
                    "name": "Engenheiro Frontend (UI/UX)",
                    "role": "Constrói interfaces responsivas HTML/CSS/JS/React conectadas às rotas reais do Backend.",
                    "model": "free:qwen-coder",
                    "x": 1030,
                    "y": 140,
                    "prompt": "Construa a interface responsiva consumindo os endpoints reais definidos pelo Backend.",
                    "terminal_cmd": "",
                    "view_mode": "split",
                    "output": "Aguardando contratos do Backend.",
                    "status": "idle",
                    "color": "#818cf8",
                },
                {
                    "id": "squad-qa",
                    "name": "QA & Revisor de Código",
                    "role": "Executa pytest, ruff/lint, py_compile, valida segurança e integração completa Front + Back + DB.",
                    "model": "free:deepseek",
                    "x": 1030,
                    "y": 470,
                    "prompt": "Rode testes e linters nos arquivos gerados/alterados, aponte bugs e valide a entrega final.",
                    "terminal_cmd": "",
                    "view_mode": "split",
                    "output": "Aguardando código de Backend e Frontend.",
                    "status": "idle",
                    "color": "#fb7185",
                },
            ],
            "edges": [
                {"id": "e-sq-1", "from": "squad-maestro", "to": "squad-db", "label": "Arquitetura"},
                {"id": "e-sq-2", "from": "squad-maestro", "to": "squad-backend", "label": "Contratos"},
                {"id": "e-sq-3", "from": "squad-db", "to": "squad-backend", "label": "Schema DB"},
                {"id": "e-sq-4", "from": "squad-backend", "to": "squad-frontend", "label": "API REST"},
                {"id": "e-sq-5", "from": "squad-backend", "to": "squad-qa", "label": "Código Back"},
                {"id": "e-sq-6", "from": "squad-frontend", "to": "squad-qa", "label": "Código Front"},
            ],
        },
        "pc_audit": {
            "name": "Auditoria & Diagnóstico Profundo do PC",
            "description": "Inspeciona rede, portas, processos e armazenamento com comandos reais no terminal.",
            "nodes": [
                {
                    "id": "audit-net",
                    "name": "Auditor de Rede & Conectividade",
                    "role": "Inspeciona interfaces de rede, IP local e conexões ativas no terminal.",
                    "model": "free:qwen-coder",
                    "x": 80,
                    "y": 80,
                    "prompt": "Analise a saída de rede do terminal e verifique se a conectividade local está saudável.",
                    "terminal_cmd": "ipconfig" if Path("C:\\").exists() else "ip addr",
                    "view_mode": "split",
                    "output": "Pronto para auditar a rede.",
                    "status": "idle",
                    "color": "#38bdf8",
                },
                {
                    "id": "audit-proc",
                    "name": "Analista de Performance & RAM",
                    "role": "Avalia processos ativos, consumo de memória e gargalos de CPU.",
                    "model": "free:openai",
                    "x": 80,
                    "y": 400,
                    "prompt": "Analise o consumo atual de CPU, RAM e Disco do PC e identifique possíveis gargalos.",
                    "terminal_cmd": "whoami",
                    "view_mode": "split",
                    "output": "Pronto para auditar processos e hardware.",
                    "status": "idle",
                    "color": "#34d399",
                },
                {
                    "id": "audit-report",
                    "name": "Consultor Chefe de Otimização",
                    "role": "Consolida os diagnósticos de rede e hardware em um laudo executivo.",
                    "model": "free:deepseek",
                    "x": 580,
                    "y": 230,
                    "prompt": "Consolide os dados de Rede e Hardware em um diagnóstico claro com 3 recomendações.",
                    "terminal_cmd": "",
                    "view_mode": "split",
                    "output": "Aguardando dados dos auditores.",
                    "status": "idle",
                    "color": "#c084fc",
                },
            ],
            "edges": [
                {"from": "audit-net", "to": "audit-report"},
                {"from": "audit-proc", "to": "audit-report"},
            ],
        },
    }


def log_activity(action_type: str, description: str) -> None:
    now = datetime.now().strftime("%H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO activity_log (action_type, description, created_at) VALUES (?, ?, ?)",
            (action_type, description, now),
        )
        conn.execute(
            """
            INSERT INTO habit_stats (action_key, count, last_used)
            VALUES (?, 1, ?)
            ON CONFLICT(action_key) DO UPDATE SET count = count + 1, last_used = excluded.last_used
            """,
            (action_type, now),
        )


def get_recent_logs(limit: int = 30) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, action_type, description, created_at FROM activity_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


# --- Tasks ---
def list_tasks(include_done: bool = True) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        if include_done:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY done ASC, CASE priority WHEN 'alta' THEN 1 WHEN 'media' THEN 2 ELSE 3 END, id DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE done = 0 ORDER BY CASE priority WHEN 'alta' THEN 1 WHEN 'media' THEN 2 ELSE 3 END, id DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def add_task(title: str, category: str = "Geral", priority: str = "media", due_time: str = "") -> Dict[str, Any]:
    priority = priority.lower().strip()
    if priority not in ("alta", "media", "baixa"):
        priority = "media"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (title, category, priority, due_time, done, created_at) VALUES (?, ?, ?, ?, 0, ?)",
            (title.strip(), category.strip() or "Geral", priority, due_time.strip(), now),
        )
        task_id = cur.lastrowid
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    log_activity("TAREFA", f"Nova tarefa criada: '{title}' ({priority})")
    return dict(row)


def toggle_task(task_id: int, done: Optional[bool] = None) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return None
        new_done = (0 if row["done"] else 1) if done is None else (1 if done else 0)
        conn.execute("UPDATE tasks SET done = ? WHERE id = ?", (new_done, task_id))
        updated = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    status_str = "concluída" if new_done else "reaberta"
    log_activity("TAREFA", f"Tarefa #{task_id} marcada como {status_str}")
    return dict(updated)


def complete_task_by_query(query: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM tasks WHERE done = 0").fetchall()
        q_lower = query.lower().strip()
        for r in rows:
            if q_lower in r["title"].lower() or str(r["id"]) == q_lower:
                return toggle_task(r["id"], True)
    return None


def delete_task(task_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        deleted = cur.rowcount > 0
    if deleted:
        log_activity("TAREFA", f"Tarefa #{task_id} removida")
    return deleted


# --- Notes ---
def list_notes() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM notes ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def add_note(title: str, content: str) -> Dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO notes (title, content, updated_at) VALUES (?, ?, ?)",
            (title.strip() or "Nota Rápida", content.strip(), now),
        )
        note_id = cur.lastrowid
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    log_activity("NOTA", f"Nota salva: '{title}'")
    return dict(row)


def delete_note(note_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        return cur.rowcount > 0


# --- Automations ---
def list_automations() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM automations ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def add_automation(
    name: str,
    schedule_type: str,
    schedule_value: str,
    action_type: str,
    action_payload: str,
) -> Dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO automations (name, schedule_type, schedule_value, action_type, action_payload, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (name.strip(), schedule_type.strip(), schedule_value.strip(), action_type.strip(), action_payload.strip(), now),
        )
        aid = cur.lastrowid
        row = conn.execute("SELECT * FROM automations WHERE id = ?", (aid,)).fetchone()
    log_activity("AUTOMAÇÃO", f"Regra criada: '{name}'")
    return dict(row)


def toggle_automation(auto_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM automations WHERE id = ?", (auto_id,)).fetchone()
        if not row:
            return None
        new_en = 0 if row["enabled"] else 1
        conn.execute("UPDATE automations SET enabled = ? WHERE id = ?", (new_en, auto_id))
        updated = conn.execute("SELECT * FROM automations WHERE id = ?", (auto_id,)).fetchone()
    return dict(updated)


def record_automation_run(auto_id: int, result_text: str) -> None:
    now = datetime.now().strftime("%H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            "UPDATE automations SET last_run = ?, last_result = ?, run_count = run_count + 1 WHERE id = ?",
            (now, result_text[:300], auto_id),
        )


def delete_automation(auto_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM automations WHERE id = ?", (auto_id,))
        return cur.rowcount > 0


# --- Smart Clipboard History ---
def list_clipboard_history(limit: int = 25) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM clipboard_history ORDER BY pinned DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def save_clipboard_item(content: str) -> Optional[Dict[str, Any]]:
    text = (content or "").strip()
    if not text or len(text) > 10000:
        return None
    cat = "Texto"
    if text.startswith(("http://", "https://", "www.")):
        cat = "Link"
    elif any(tok in text for tok in ("def ", "function ", "import ", "const ", "SELECT ", "{", "=>", "class ")):
        cat = "Código"

    now = datetime.now().strftime("%H:%M:%S")
    with get_conn() as conn:
        # Avoid consecutive duplicate
        latest = conn.execute("SELECT content FROM clipboard_history ORDER BY id DESC LIMIT 1").fetchone()
        if latest and latest["content"] == text:
            return None
        # Remove older identical unpinned entry
        conn.execute("DELETE FROM clipboard_history WHERE content = ? AND pinned = 0", (text,))
        cur = conn.execute(
            "INSERT INTO clipboard_history (content, category, pinned, created_at) VALUES (?, ?, 0, ?)",
            (text, cat, now),
        )
        cid = cur.lastrowid
        # Keep history trimmed
        conn.execute(
            "DELETE FROM clipboard_history WHERE pinned = 0 AND id NOT IN (SELECT id FROM clipboard_history ORDER BY id DESC LIMIT 40)"
        )
        row = conn.execute("SELECT * FROM clipboard_history WHERE id = ?", (cid,)).fetchone()
        return dict(row) if row else None


def toggle_pin_clipboard(clip_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM clipboard_history WHERE id = ?", (clip_id,)).fetchone()
        if not row:
            return None
        new_pin = 0 if row["pinned"] else 1
        conn.execute("UPDATE clipboard_history SET pinned = ? WHERE id = ?", (new_pin, clip_id))
        updated = conn.execute("SELECT * FROM clipboard_history WHERE id = ?", (clip_id,)).fetchone()
        return dict(updated)


def delete_clipboard_item(clip_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM clipboard_history WHERE id = ?", (clip_id,))
        return cur.rowcount > 0


# --- Maestri Canvas State ---
def get_canvas_state() -> Dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT nodes_json, edges_json, updated_at FROM canvas_state WHERE id = 1").fetchone()
        if not row:
            return {"nodes": [], "edges": [], "updated_at": ""}
        return {
            "nodes": json.loads(row["nodes_json"]),
            "edges": json.loads(row["edges_json"]),
            "updated_at": row["updated_at"],
        }


def save_canvas_state(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO canvas_state (id, nodes_json, edges_json, updated_at)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                nodes_json = excluded.nodes_json,
                edges_json = excluded.edges_json,
                updated_at = excluded.updated_at
            """,
            (json.dumps(nodes, ensure_ascii=False), json.dumps(edges, ensure_ascii=False), now),
        )
    return get_canvas_state()


def load_maestri_template(template_key: str) -> Dict[str, Any]:
    templates = get_maestri_templates()
    tpl = templates.get(template_key) or templates["default"]
    state = save_canvas_state(tpl["nodes"], tpl["edges"])
    log_activity("MAESTRI", f"Template carregado: {tpl['name']}")
    return state


# --- Synced User Applications ---
def save_synced_apps_batch(apps: List[Dict[str, str]]) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    count = 0
    with get_conn() as conn:
        for a in apps:
            app_id = a["id"].lower().strip()
            if not app_id:
                continue
            conn.execute(
                """
                INSERT INTO synced_apps (id, name, target_path, exe_name, category, icon, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    target_path = excluded.target_path,
                    exe_name = excluded.exe_name,
                    category = excluded.category,
                    icon = excluded.icon,
                    updated_at = excluded.updated_at
                """,
                (
                    app_id,
                    a.get("name", app_id),
                    a.get("target_path", ""),
                    a.get("exe_name", ""),
                    a.get("category", "Sistema"),
                    a.get("icon", "app-window"),
                    a.get("source", "auto"),
                    now,
                ),
            )
            count += 1
    return count


def list_synced_apps() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM synced_apps ORDER BY category ASC, name ASC").fetchall()
        return [dict(r) for r in rows]


def delete_synced_app(app_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM synced_apps WHERE id = ?", (app_id.lower().strip(),))
        return cur.rowcount > 0


# --- Settings ---
def get_settings() -> Dict[str, Any]:
    defaults = {
        "assistant_name": "AURA",
        "response_style": "direto_tecnico",
        "custom_system_prompt": "",
        "ai_provider": "free_pool",
        "default_free_model": "free:openai",
        "gemini_api_key": "",
        "gemini_model": "gemini-3.8-flash",
        "groq_api_key": "",
        "openrouter_api_key": "",
        "ollama_url": "http://localhost:11434",
        "ollama_model": "llama3.2",
        "voice_reply": True,
        "voice_rate": 1.08,
        "auto_learn_memory": True,
        "terminal_input_mode": "agent_and_shell",
        "agent_auto_exec_shell": True,
        "default_terminal_cwd": str(Path.home()),
        "terminal_timeout_sec": 30,
        "hud_compact_w": 735,
        "hud_expanded_w": 750,
        "hud_expanded_h": 510,
        "notify_on_maestri": True,
        "notify_on_terminal": True,
        "notify_on_chat": True,
        "hardware_alert_threshold": 88,
        "auto_update_enabled": True,
        "update_repo": "HigorAmaral/aura-assistant",
        "update_branch": "main",
        "update_check_interval_sec": 60,
        "auto_restart_on_update": True,
        "remote_pin": "",
        "active_workspace": str(Path.cwd()),
        "global_env_vars": {},
    }
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        for r in rows:
            try:
                defaults[r["key"]] = json.loads(r["value"])
            except Exception:
                defaults[r["key"]] = r["value"]
    return defaults


def update_settings(new_settings: Dict[str, Any]) -> Dict[str, Any]:
    with get_conn() as conn:
        for k, v in new_settings.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, json.dumps(v)),
            )
    log_activity("CONFIG", "Configurações do sistema atualizadas")
    return get_settings()


def clear_activity_logs() -> int:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM activity_log")
        return cur.rowcount


# --- Persistent Chat History ---
def get_chat_history(limit: int = 20) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, role, content, provider, created_at FROM chat_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def append_chat_history(role: str, content: str, provider: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO chat_history (role, content, provider, created_at) VALUES (?, ?, ?, ?)",
            (role, content[:6000], provider, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.execute(
            "DELETE FROM chat_history WHERE id NOT IN (SELECT id FROM chat_history ORDER BY id DESC LIMIT 100)"
        )


def clear_chat_history() -> int:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM chat_history")
        return cur.rowcount


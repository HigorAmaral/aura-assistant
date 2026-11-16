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
                ("Explorar a Central IA & PC e o Terminal Rápido", "Sistema", "alta", "Hoje", 0, now),
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
                ("Ambiente", "O usuário utiliza a AURA OS como assistente pessoal do computador e barra superior em segundo plano.", 1.0, "sistema", now),
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
        "notify_on_tasks": True,
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


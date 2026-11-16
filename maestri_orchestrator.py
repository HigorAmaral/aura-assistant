import json
import os
import re
import shutil
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from storage import get_canvas_state, save_canvas_state, log_activity
from terminal_manager import append_terminal_log, get_or_init_terminal_session
from ai_engine import run_maestri_canvas_agent
from free_ai_router import call_with_free_ai_failover
from remote_bridge import push_mobile_notification
from project_builder import (
    PROJECTS_ROOT,
    is_project_build_intent,
    _slugify,
    scaffold_database_layer,
    scaffold_backend_layer,
    scaffold_frontend_layer,
    launch_generated_project,
)


EXTERNAL_CLIS = [
    ("gh", "GitHub CLI"),
    ("vercel", "Vercel CLI"),
    ("supabase", "Supabase CLI"),
    ("antigravity", "Antigravity"),
    ("git", "Git"),
    ("python", "Python"),
    ("node", "Node.js"),
    ("npm", "NPM"),
    ("npx", "NPX"),
    ("powershell", "PowerShell"),
    ("pwsh", "PowerShell 7"),
    ("wsl", "WSL Linux"),
    ("code", "VS Code"),
    ("docker", "Docker"),
    ("ollama", "Ollama"),
    ("gemini", "Gemini CLI"),
    ("claude", "Claude Code CLI"),
    ("codex", "Codex CLI"),
    ("aider", "Aider CLI"),
]


def _resolve_cli_path(cmd: str) -> Dict[str, Any]:
    path = shutil.which(cmd)
    if path:
        return {"installed": True, "via_npx": False, "path": path}

    if cmd == "antigravity" and os.name == "nt":
        local_app = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            Path(local_app) / "Programs" / "antigravity" / "Antigravity.exe",
            Path(local_app) / "Programs" / "Antigravity" / "Antigravity.exe",
        ]
        for p in candidates:
            if p.exists():
                return {"installed": True, "via_npx": False, "path": str(p)}
        agy_path = shutil.which("agy")
        if agy_path:
            return {"installed": True, "via_npx": False, "path": agy_path}

    if cmd == "vercel":
        vc_path = shutil.which("vc")
        if vc_path:
            return {"installed": True, "via_npx": False, "path": vc_path}

    if cmd in ("vercel", "supabase") and shutil.which("npx"):
        return {"installed": True, "via_npx": True, "path": f"npx {cmd}"}

    return {"installed": False, "via_npx": False, "path": ""}


def detect_installed_clis() -> List[Dict[str, Any]]:
    found = []
    for cmd, label in EXTERNAL_CLIS:
        info = _resolve_cli_path(cmd)
        found.append({
            "cmd": cmd,
            "label": label,
            "installed": info["installed"],
            "via_npx": info["via_npx"],
            "path": info["path"],
        })
    return found


def install_cli_tool(cli_cmd: str) -> Dict[str, Any]:
    """Install global CLI tools like vercel, supabase, or gh."""
    c = cli_cmd.strip().lower()
    npm_bin = shutil.which("npm")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    if c in ("vercel", "supabase"):
        if not npm_bin:
            return {"success": False, "message": "NPM não encontrado no PATH para instalar automaticamente."}
        try:
            res = subprocess.run(
                [npm_bin, "install", "-g", c],
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=flags,
            )
            if res.returncode == 0:
                return {"success": True, "message": f"CLI '{c}' instalada globalmente com sucesso!"}
            return {"success": False, "message": res.stderr.strip() or res.stdout.strip() or f"Falha ao instalar {c}."}
        except Exception as exc:
            return {"success": False, "message": f"Erro ao instalar {c}: {exc}"}

    if c == "gh" and os.name == "nt" and shutil.which("winget"):
        try:
            res = subprocess.run(
                ["winget", "install", "--id", "GitHub.cli", "-e", "--silent"],
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=flags,
            )
            if res.returncode == 0:
                return {"success": True, "message": "GitHub CLI (gh) instalada com sucesso!"}
            return {"success": False, "message": res.stderr.strip() or "Falha ao instalar GitHub CLI."}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    return {"success": False, "message": f"Instalação automática não suportada para '{c}'."}


def detect_runmaestro() -> Dict[str, Any]:
    candidates = []
    if os.name == "nt":
        local_app = os.environ.get("LOCALAPPDATA", "")
        prog_files = os.environ.get("ProgramFiles", "")
        candidates.extend([
            Path(local_app) / "Programs" / "Maestro" / "Maestro.exe",
            Path(local_app) / "Maestro" / "Maestro.exe",
            Path(prog_files) / "Maestro" / "Maestro.exe",
        ])
    else:
        which_m = shutil.which("maestro")
        if which_m:
            candidates.append(Path(which_m))

    for p in candidates:
        if p and p.exists():
            return {"installed": True, "path": str(p), "repo_url": "https://github.com/RunMaestro/Maestro"}

    return {
        "installed": False,
        "path": "",
        "repo_url": "https://github.com/RunMaestro/Maestro",
        "releases_url": "https://github.com/RunMaestro/Maestro/releases/latest",
    }


def launch_or_open_runmaestro() -> Dict[str, Any]:
    info = detect_runmaestro()
    if info["installed"]:
        try:
            subprocess.Popen([info["path"]], close_fds=True)
            return {"success": True, "launched": True, "message": f"RunMaestro iniciado: {info['path']}"}
        except Exception as exc:
            return {"success": False, "message": f"Falha ao iniciar RunMaestro: {exc}"}

    # Open RunMaestro releases page in browser so user can download the Windows installer if desired
    import webbrowser
    webbrowser.open(info["releases_url"])
    return {
        "success": True,
        "launched": False,
        "opened_url": info["releases_url"],
        "message": "RunMaestro não encontrado localmente. Abrimos a página oficial de releases (RunMaestro/Maestro) no navegador.",
    }


def ipc_check() -> Dict[str, Any]:
    """Equivalent to `omaestri check`: return live status of all agent blocks on the 2D canvas."""
    state = get_canvas_state()
    nodes = state.get("nodes", [])
    edges = state.get("edges", [])
    summary = []
    for n in nodes:
        nid = n.get("id", "")
        term = get_or_init_terminal_session(nid)
        summary.append({
            "id": nid,
            "name": n.get("name", nid),
            "role": n.get("role", ""),
            "model": n.get("model", "free:openai"),
            "cwd": term.get("cwd", ""),
            "last_output": (n.get("last_output") or "")[:240],
        })
    return {"ok": True, "count": len(summary), "nodes": summary, "edges": edges}


def _find_node(nodes: List[Dict[str, Any]], target: str) -> Optional[Dict[str, Any]]:
    t = target.strip().lower()
    for n in nodes:
        if (n.get("id") or "").lower() == t:
            return n
    for n in nodes:
        if (n.get("name") or "").lower() == t:
            return n
    for n in nodes:
        if t in (n.get("name") or "").lower() or t in (n.get("role") or "").lower():
            return n
    return None


def ipc_ask(target: str, prompt: str) -> Dict[str, Any]:
    """Equivalent to `omaestri ask`: send a task to another agent block and return its live result."""
    state = get_canvas_state()
    nodes = state.get("nodes", [])
    edges = state.get("edges", [])
    node = _find_node(nodes, target)
    if not node:
        return {"ok": False, "error": f"Bloco/agente '{target}' não encontrado no canvas."}

    res = run_maestri_canvas_agent(
        node_id=node["id"],
        agent_name=node.get("name", node["id"]),
        agent_role=node.get("role", ""),
        prompt=prompt,
        model_id=node.get("model", "free:openai"),
        upstream_outputs=[],
    )
    node["last_output"] = res.get("output", "")
    save_canvas_state(nodes, edges)
    return {"ok": True, "node_id": node["id"], "name": node.get("name"), "result": res}


def ipc_spawn(
    name: str,
    role: str,
    prompt: str = "",
    model: str = "free:openai",
    connect_from_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new agent block on the Maestri 2D canvas, connect it from Maestro, and optionally execute it."""
    state = get_canvas_state()
    nodes = state.get("nodes", [])
    edges = state.get("edges", [])

    maestro_node = _find_node(nodes, "maestro")
    source_id = connect_from_id or (maestro_node["id"] if maestro_node else (nodes[0]["id"] if nodes else None))

    idx = len(nodes)
    new_id = f"node-{uuid.uuid4().hex[:8]}"
    new_node = {
        "id": new_id,
        "name": name,
        "role": role,
        "model": model,
        "x": 120 + (idx % 3) * 380,
        "y": 140 + (idx // 3) * 320,
        "last_output": "",
    }
    nodes.append(new_node)
    if source_id and source_id != new_id:
        edges.append({"id": f"edge-{uuid.uuid4().hex[:6]}", "from": source_id, "to": new_id})

    save_canvas_state(nodes, edges)

    exec_res = None
    if prompt.strip():
        exec_res = run_maestri_canvas_agent(
            node_id=new_id,
            agent_name=name,
            agent_role=role,
            prompt=prompt,
            model_id=model,
            upstream_outputs=[],
        )
        new_node["last_output"] = exec_res.get("output", "")
        save_canvas_state(nodes, edges)

    return {"ok": True, "node": new_node, "execution": exec_res}


_MAESTRO_LIVE_STATE: Dict[str, Any] = {
    "running": False,
    "phase": "idle",
    "goal": "",
    "strategy": "",
    "started_at": 0.0,
    "elapsed_sec": 0.0,
    "node_states": {},
    "active_edges": [],
}


def get_maestro_live_status() -> Dict[str, Any]:
    st = dict(_MAESTRO_LIVE_STATE)
    if st.get("running") and st.get("started_at"):
        st["elapsed_sec"] = round(time.time() - float(st["started_at"]), 1)
    return st


def _set_maestro_state(**kwargs: Any) -> None:
    _MAESTRO_LIVE_STATE.update(kwargs)


def _set_node_live(node_id: str, status: str, step: str = "") -> None:
    ns = _MAESTRO_LIVE_STATE.setdefault("node_states", {})
    ns[node_id] = {"status": status, "step": step}


def run_maestro_mode(goal: str) -> Dict[str, Any]:
    """
    Modo Maestro (estilo Maestri oficial / omaestri):
    - Fase 1: Planejamento estratégico via IA (decomposição DAG + spawn dinâmico de especialistas)
    - Fase 2: Execução em ondas (paralela + dependências upstream) com ReAct de 5 ciclos e IPC
    - Fase 3: Auditoria de qualidade do Maestro (recuperação automática de falhas)
    - Fase 4: Síntese executiva sênior + telemetria ao vivo no canvas + notificação mobile
    """
    t0 = time.time()
    _set_maestro_state(
        running=True,
        phase="planning",
        goal=goal,
        strategy="Analisando objetivo e montando plano estratégico...",
        started_at=t0,
        elapsed_sec=0.0,
        node_states={},
        active_edges=[],
    )

    state = get_canvas_state()
    nodes = state.get("nodes", [])
    edges = state.get("edges", [])

    maestro_node = _find_node(nodes, "maestro")
    if not maestro_node:
        maestro_node = {
            "id": "node-maestro",
            "name": "Maestro Orquestrador",
            "role": "Arquiteto-chefe do canvas: planeja em DAG, spawna especialistas, audita entregas e sintetiza.",
            "model": "free:deepseek",
            "x": 80,
            "y": 80,
            "status": "running",
            "last_output": "",
        }
        nodes.insert(0, maestro_node)
    else:
        maestro_node["status"] = "running"

    _set_node_live(maestro_node["id"], "running", "Planejando missão...")

    workers = [n for n in nodes if n["id"] != maestro_node["id"]]
    if not workers:
        default_workers = [
            ("Engenheiro Sistema & CLIs", "Executa comandos reais no PC, Git, Python, código e analisa arquivos locais.", "free:qwen-coder"),
            ("Pesquisador Web & GitHub", "Pesquisa na web em tempo real, lê documentação e consulta repositórios no GitHub.", "free:mistral"),
        ]
        for i, (w_name, w_role, w_model) in enumerate(default_workers):
            w_id = f"node-worker-{i+1}"
            w_node = {"id": w_id, "name": w_name, "role": w_role, "model": w_model, "x": 560, "y": 60 + i * 320, "status": "idle", "last_output": ""}
            nodes.append(w_node)
            edges.append({"id": f"edge-m-{i+1}", "from": maestro_node["id"], "to": w_id})
            workers.append(w_node)

    save_canvas_state(nodes, edges)

    append_terminal_log(
        node_id=maestro_node["id"],
        header_cmd=f"aura-maestro❯ {goal}",
        output_body=(
            f"⚙ [MODO MAESTRO ATIVADO] Analisando objetivo com {len(workers)} agente(s) no canvas..."
        ),
    )

    if is_project_build_intent(goal):
        _set_maestro_state(phase="executing", strategy=f"Construção Full-Stack automática: {goal}")
        slug = _slugify(goal)
        project_dir = PROJECTS_ROOT / slug
        w_db = workers[0]
        w_be = workers[1] if len(workers) > 1 else workers[0]
        w_fe = workers[2] if len(workers) > 2 else workers[-1]

        _set_node_live(w_db["id"], "running", "Criando banco SQLite...")
        db_info = scaffold_database_layer(project_dir, goal)
        db_msg = f"✔ Banco SQLite criado em {db_info['file']} | Tabelas: {', '.join(db_info['tables'])} ({db_info['seed_count']} itens iniciais)"
        w_db["last_output"] = db_msg
        w_db["status"] = "done"
        _set_node_live(w_db["id"], "done", "Banco SQLite pronto")
        append_terminal_log(w_db["id"], f"aura-agent❯ Criar Banco de Dados ({slug})", db_msg)

        _set_node_live(w_be["id"], "running", "Criando API FastAPI...")
        be_info = scaffold_backend_layer(project_dir, goal)
        be_msg = f"✔ Backend FastAPI criado em {be_info['file']} | Rotas: {', '.join(be_info['endpoints'])}"
        w_be["last_output"] = be_msg
        w_be["status"] = "done"
        _set_node_live(w_be["id"], "done", "Backend FastAPI pronto")
        append_terminal_log(w_be["id"], f"aura-agent❯ Criar Backend FastAPI ({slug})", be_msg)

        _set_node_live(w_fe["id"], "running", "Criando Frontend & subindo servidor...")
        fe_info = scaffold_frontend_layer(project_dir, goal)
        launch_info = launch_generated_project(project_dir)
        fe_msg = (
            f"✔ Frontend criado em {fe_info['file']}\n"
            f"✔ Servidor local {'ONLINE' if launch_info['ok'] else 'iniciado'} em: {launch_info['url']} (PID {launch_info['pid']})"
        )
        w_fe["last_output"] = fe_msg
        w_fe["status"] = "done"
        _set_node_live(w_fe["id"], "done", "Servidor online")
        append_terminal_log(w_fe["id"], f"aura-agent❯ Criar Frontend & Iniciar Servidor ({slug})", fe_msg)

        elapsed = round(time.time() - t0, 2)
        consolidated_text = (
            f"✔ [PROJETO CONSTRUÍDO & RODANDO em {elapsed}s]\n"
            f"📁 Pasta do Projeto: {project_dir}\n"
            f"🌐 URL Local (Front + Back + SQLite): {launch_info['url']}\n"
            f"🗄 Banco de Dados: {project_dir / 'app.db'} (tabelas: products, orders)\n"
            f"📄 Arquivos: database.py, app.py, static/index.html\n\n"
            f"═══ ENTREGAS DOS AGENTES ═══\n"
            f"• [{w_db['name']}]: {db_msg}\n"
            f"• [{w_be['name']}]: {be_msg}\n"
            f"• [{w_fe['name']}]: {fe_msg}"
        )
        maestro_node["last_output"] = consolidated_text
        maestro_node["status"] = "done"
        save_canvas_state(nodes, edges)
        append_terminal_log(maestro_node["id"], "aura-maestro❯ [CONSOLIDAÇÃO FINAL]", consolidated_text)
        log_activity("MAESTRO", f"Projeto '{slug}' construído e rodando em {launch_info['url']}")
        _set_maestro_state(running=False, phase="done", elapsed_sec=elapsed, active_edges=[])
        _set_node_live(maestro_node["id"], "done", f"Concluído em {elapsed}s")
        try:
            push_mobile_notification(
                title="Projeto Pronto & Rodando!",
                body=f"{slug} está online em {launch_info['url']} ({project_dir})",
                category="MAESTRI",
                agent_name="Maestro Orquestrador",
            )
        except Exception:
            pass
        return {
            "ok": True,
            "elapsed_sec": elapsed,
            "maestro_node_id": maestro_node["id"],
            "project_dir": str(project_dir),
            "url": launch_info["url"],
            "workers": [
                {"node_id": w_db["id"], "name": w_db["name"], "output": db_msg, "provider": "AURA Project Builder"},
                {"node_id": w_be["id"], "name": w_be["name"], "output": be_msg, "provider": "AURA Project Builder"},
                {"node_id": w_fe["id"], "name": w_fe["name"], "output": fe_msg, "provider": "AURA Project Builder"},
            ],
            "consolidated": consolidated_text,
        }

    # --- FASE 1: Planejamento Estratégico DAG + Spawn Dinâmico ---
    worker_catalog = "\n".join(
        [f"- id: {w['id']} | nome: {w.get('name')} | papel: {w.get('role')} | modelo: {w.get('model')}" for w in workers]
    )
    planner_sys = (
        "Você é o Maestro Orquestrador Sênior do AURA OS (estilo RunMaestro/omaestri).\n"
        "Decomponha o objetivo em um plano de execução em ondas (DAG) para os agentes do canvas.\n"
        "Regras:\n"
        "1. Atribua missões específicas, técnicas e NÃO-REDUNDANTES para os agentes existentes.\n"
        "2. Se faltar um especialista essencial para o objetivo (máximo 1 novo agente), você pode incluí-lo em `spawn_agents`.\n"
        "3. Use `depends_on` (lista de node_id) somente quando um agente precisar do resultado de outro antes de começar.\n"
        "Responda EXCLUSIVAMENTE com um JSON válido:\n"
        "{\n"
        '  "strategy": "Estratégia clara e técnica em 1 frase",\n'
        '  "assignments": [\n'
        '    {"node_id": "id_do_bloco", "task": "Missão específica e acionável", "cmd": "comando shell opcional ou vazio", "depends_on": []}\n'
        "  ],\n"
        '  "spawn_agents": [\n'
        '    {"name": "Nome Especialista", "role": "Papel técnico", "model": "free:qwen-coder", "task": "Missão do novo agente", "cmd": ""}\n'
        "  ]\n"
        "}"
    )
    planner_user = (
        f"OBJETIVO DO USUÁRIO: {goal}\n"
        f"SISTEMA OPERACIONAL: {'Windows' if os.name == 'nt' else 'Linux'}\n"
        f"AGENTES DISPONÍVEIS NO CANVAS:\n{worker_catalog}\n\n"
        "Crie o plano estratégico JSON."
    )

    plan_data: Dict[str, Any] = {}
    try:
        plan_res = call_with_free_ai_failover(
            user_prompt=planner_user,
            system_prompt=planner_sys,
            preferred_model_id=maestro_node.get("model", "free:deepseek"),
            task_type="planning",
        )
        if plan_res.get("success") and plan_res.get("reply"):
            raw = plan_res["reply"].strip()
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                plan_data = json.loads(m.group(0))
    except Exception:
        plan_data = {}

    strategy_text = plan_data.get("strategy") or f"Execução coordenada em ondas para: {goal}"
    _set_maestro_state(phase="spawning", strategy=strategy_text)

    assignment_map: Dict[str, Dict[str, Any]] = {}
    for item in plan_data.get("assignments", []) if isinstance(plan_data.get("assignments"), list) else []:
        if isinstance(item, dict) and item.get("node_id"):
            assignment_map[str(item["node_id"])] = {
                "task": str(item.get("task") or "").strip(),
                "cmd": str(item.get("cmd") or "").strip(),
                "depends_on": [str(d) for d in (item.get("depends_on") or []) if d],
            }

    # Dynamic specialist spawning (up to 1 new specialist per run to keep canvas clean)
    spawn_list = plan_data.get("spawn_agents", []) if isinstance(plan_data.get("spawn_agents"), list) else []
    for sp in spawn_list[:1]:
        if isinstance(sp, dict) and sp.get("name") and sp.get("task"):
            new_id = f"node-sp-{uuid.uuid4().hex[:6]}"
            idx = len(nodes)
            sp_node = {
                "id": new_id,
                "name": str(sp["name"])[:40],
                "role": str(sp.get("role") or "Especialista dinâmico criado pelo Maestro"),
                "model": str(sp.get("model") or "free:qwen-coder"),
                "x": 560 + (idx % 2) * 490,
                "y": 60 + (idx // 2) * 320,
                "status": "idle",
                "last_output": "",
            }
            nodes.append(sp_node)
            edges.append({"id": f"edge-sp-{uuid.uuid4().hex[:5]}", "from": maestro_node["id"], "to": new_id})
            workers.append(sp_node)
            assignment_map[new_id] = {
                "task": str(sp["task"]).strip(),
                "cmd": str(sp.get("cmd") or "").strip(),
                "depends_on": [],
            }

    save_canvas_state(nodes, edges)

    append_terminal_log(
        node_id=maestro_node["id"],
        header_cmd="aura-maestro❯ [PLANO ESTRATÉGICO DAG]",
        output_body=(
            f"🧠 Estratégia: {strategy_text}\n"
            + "\n".join(
                [
                    f"├─ 🎯 [{w.get('name')}]: {assignment_map.get(w['id'], {}).get('task') or 'Missão alinhada ao papel: ' + str(w.get('role', ''))}"
                    for w in workers
                ]
            )
        ),
    )

    # --- FASE 2: Execução em Ondas (Paralela + Dependências DAG) ---
    _set_maestro_state(
        phase="executing",
        active_edges=[{"from": maestro_node["id"], "to": w["id"]} for w in workers],
    )
    node_by_id = {n["id"]: n for n in nodes}
    worker_results_map: Dict[str, Dict[str, Any]] = {}
    completed_ids: set[str] = set()
    pending_workers = list(workers)

    def _run_worker(w: Dict[str, Any]) -> Dict[str, Any]:
        w["status"] = "running"
        _set_node_live(w["id"], "running", "Iniciando agente...")
        assigned = assignment_map.get(w["id"], {})
        specific_task = assigned.get("task") or (
            f"Contribua com sua especialidade ({w.get('role')}) para resolver o objetivo."
        )
        sub_prompt = (
            f"OBJETIVO GLOBAL: {goal}\n"
            f"ESTRATÉGIA DO MAESTRO: {strategy_text}\n\n"
            f"SUA MISSÃO ESPECÍFICA ({w.get('name')}):\n{specific_task}"
        )
        upstream = []
        dep_ids = set(assigned.get("depends_on") or [])
        for ed in edges:
            if ed.get("to") == w["id"]:
                dep_ids.add(ed.get("from"))
        for src_id in dep_ids:
            src = node_by_id.get(src_id)
            if src and src.get("id") != maestro_node["id"] and src.get("last_output"):
                upstream.append({"name": src.get("name", src["id"]), "output": src["last_output"]})

        res = run_maestri_canvas_agent(
            node_id=w["id"],
            agent_name=w.get("name", w["id"]),
            agent_role=w.get("role", ""),
            prompt=sub_prompt,
            model_id=w.get("model", "free:openai"),
            terminal_cmd=assigned.get("cmd", ""),
            upstream_outputs=upstream,
            on_step=lambda msg, wid=w["id"]: _set_node_live(wid, "running", msg[:90]),
        )
        w["last_output"] = res.get("output", "")
        ok_flag = bool(res.get("success", True) and w["last_output"].strip())
        w["status"] = "done" if ok_flag else "error"
        _set_node_live(w["id"], w["status"], f"Concluído ({res.get('elapsed_s', 0)}s)")
        provider_used = res.get("provider_used") or res.get("provider") or "AURA"
        return {
            "node_id": w["id"],
            "name": w.get("name"),
            "task": specific_task,
            "output": w["last_output"],
            "provider": provider_used,
            "ok": ok_flag,
        }

    # Execute in topological waves respecting BOTH AI depends_on AND user-drawn canvas edges
    worker_id_set = {wk["id"] for wk in workers}
    for _wave in range(len(workers) + 1):
        if not pending_workers:
            break
        ready = []
        deferred = []
        for w in pending_workers:
            ai_deps = set(assignment_map.get(w["id"], {}).get("depends_on", []))
            edge_deps = {ed.get("from") for ed in edges if ed.get("to") == w["id"] and ed.get("from") in worker_id_set}
            deps = [d for d in (ai_deps | edge_deps) if d in worker_id_set and d != w["id"]]
            if all(d in completed_ids for d in deps):
                ready.append(w)
            else:
                deferred.append(w)
        if not ready:
            ready = pending_workers
            deferred = []

        with ThreadPoolExecutor(max_workers=min(4, max(1, len(ready)))) as pool:
            futures = {pool.submit(_run_worker, w): w for w in ready}
            for fut in as_completed(futures):
                wk = futures[fut]
                try:
                    wr = fut.result()
                except Exception as exc:
                    wk["status"] = "error"
                    _set_node_live(wk["id"], "error", str(exc)[:80])
                    wr = {"node_id": wk["id"], "name": wk.get("name", "Worker"), "task": "", "output": f"Erro: {exc}", "provider": "error", "ok": False}
                worker_results_map[wk["id"]] = wr
                completed_ids.add(wk["id"])
        pending_workers = deferred

    worker_results = [worker_results_map[w["id"]] for w in workers if w["id"] in worker_results_map]

    # --- FASE 3: Auditoria de Qualidade do Maestro (Self-Correction Gate) ---
    _set_maestro_state(phase="auditing", active_edges=[])
    _set_node_live(maestro_node["id"], "running", "Auditando entregas dos agentes...")
    failed_workers = [wr for wr in worker_results if not wr.get("ok") or len(wr.get("output", "").strip()) < 25]
    if failed_workers:
        append_terminal_log(
            node_id=maestro_node["id"],
            header_cmd="aura-maestro❯ [AUDITORIA DE QUALIDADE]",
            output_body=f"🔍 Detectadas {len(failed_workers)} entrega(s) incompleta(s). Executando recuperação automática...",
        )
        for fw in failed_workers[:2]:
            w_obj = node_by_id.get(fw["node_id"])
            if w_obj:
                retry_res = run_maestri_canvas_agent(
                    node_id=w_obj["id"],
                    agent_name=w_obj.get("name", w_obj["id"]),
                    agent_role=w_obj.get("role", ""),
                    prompt=f"REVISÃO SOLICITADA PELO MAESTRO para o objetivo '{goal}':\n{fw.get('task')}\nEntregue uma análise concreta e completa.",
                    model_id="free:deepseek",
                    upstream_outputs=[],
                )
                if retry_res.get("output"):
                    fw["output"] = retry_res["output"]
                    fw["provider"] = retry_res.get("provider_used", "AURA Recovery")
                    fw["ok"] = True
                    w_obj["last_output"] = fw["output"]
                    w_obj["status"] = "done"
                    _set_node_live(w_obj["id"], "done", "Recuperado na auditoria")

    # --- FASE 4: Síntese Executiva Sênior do Maestro ---
    _set_maestro_state(phase="synthesizing")
    _set_node_live(maestro_node["id"], "running", "Gerando síntese executiva...")
    raw_deliveries = "\n\n".join(
        [f"### [{wr['name']}] ({wr['provider']})\nMissão: {wr.get('task', '')}\nEntrega:\n{wr['output'][:2200]}" for wr in worker_results]
    )
    synth_sys = (
        "Você é o Maestro Orquestrador Sênior do AURA OS. Consolide as entregas dos agentes especialistas abaixo em um "
        "Relatório Executivo de nível profissional em Português do Brasil.\n"
        "Estruture obrigatoriamente em:\n"
        "1. **Resumo Executivo** (resposta direta ao objetivo)\n"
        "2. **Achados & Evidências Concretas** (arquivos, comandos, métricas, URLs reais coletados)\n"
        "3. **Próximos Passos Recomendados** (ações práticas e imediatas)\n"
        "Elimine redundâncias e nunca invente dados que não estejam nas entregas."
    )
    synth_user = f"OBJETIVO ORIGINAL: {goal}\nESTRATÉGIA: {strategy_text}\n\nENTREGAS DOS AGENTES:\n{raw_deliveries}"

    synthesized_reply = ""
    try:
        synth_res = call_with_free_ai_failover(
            user_prompt=synth_user,
            system_prompt=synth_sys,
            preferred_model_id=maestro_node.get("model", "free:deepseek"),
            task_type="synthesis",
        )
        if synth_res.get("success") and synth_res.get("reply"):
            synthesized_reply = synth_res["reply"].strip()
    except Exception:
        synthesized_reply = ""

    elapsed = round(time.time() - t0, 2)
    if synthesized_reply:
        consolidated_text = (
            f"✔ [MAESTRO CONCLUÍDO em {elapsed}s] {len(worker_results)} agente(s) coordenado(s) para: \"{goal}\"\n\n"
            f"═══ SÍNTESE EXECUTIVA DO MAESTRO ═══\n{synthesized_reply}\n\n"
            f"═══ DETALHES POR AGENTE ═══\n"
            + "\n".join([f"• [{wr['name']}] ({wr['provider']}): {wr['output'][:280]}..." for wr in worker_results])
        )
    else:
        consolidated_lines = [
            f"✔ [MAESTRO CONCLUÍDO em {elapsed}s] Consolidação de {len(worker_results)} agente(s) para: \"{goal}\"\n",
            "═══ ENTREGAS DO TIME ═══",
        ]
        for wr in worker_results:
            consolidated_lines.append(f"\n▶ [{wr['name']}] ({wr['provider']}):\n{wr['output'][:900]}")
        consolidated_text = "\n".join(consolidated_lines)

    maestro_node["last_output"] = consolidated_text
    maestro_node["status"] = "done"
    save_canvas_state(nodes, edges)

    _set_maestro_state(running=False, phase="done", elapsed_sec=elapsed, active_edges=[])
    _set_node_live(maestro_node["id"], "done", f"Concluído em {elapsed}s")

    append_terminal_log(
        node_id=maestro_node["id"],
        header_cmd="aura-maestro❯ [CONSOLIDAÇÃO FINAL]",
        output_body=consolidated_text,
    )

    log_activity("MAESTRO", f"Modo Maestro concluiu '{goal[:60]}' com {len(worker_results)} agentes em {elapsed}s")
    try:
        push_mobile_notification(
            title="Modo Maestro Concluído",
            body=f"Objetivo '{goal[:80]}' finalizado por {len(worker_results)} agentes em {elapsed}s.",
            category="MAESTRI",
            agent_name="Maestro Orquestrador",
        )
    except Exception:
        pass

    return {
        "ok": True,
        "elapsed_sec": elapsed,
        "maestro_node_id": maestro_node["id"],
        "strategy": strategy_text,
        "workers": worker_results,
        "consolidated": consolidated_text,
    }

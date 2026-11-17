import asyncio
import json
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, StreamingResponse, JSONResponse
from pydantic import BaseModel

from storage import (
    init_db,
    list_tasks,
    add_task,
    toggle_task,
    delete_task,
    list_notes,
    add_note,
    delete_note,
    get_settings,
    update_settings,
    get_recent_logs,
    list_automations,
    add_automation,
    toggle_automation,
    delete_automation,
    list_clipboard_history,
    toggle_pin_clipboard,
    delete_clipboard_item,
    save_synced_apps_batch,
    delete_synced_app,
    clear_activity_logs,
    get_chat_history,
    clear_chat_history,
    export_all_data,
)
from system_tools import (
    get_system_stats,
    get_top_processes,
    kill_process_by_pid,
    open_application,
    close_application,
    get_quick_apps_catalog,
    sync_installed_apps,
    take_screenshot,
    media_and_volume_control,
    clean_temp_files,
    empty_recycle_bin,
    lock_workstation,
    run_productivity_routine,
    get_background_status,
    toggle_windows_autostart,
    create_desktop_launcher,
    get_network_diagnostics,
    power_control,
    get_open_ports,
    get_dev_environment_info,
    IS_WINDOWS,
)
from file_tools import (
    search_local_files,
    organize_directory,
    create_text_file,
)
from web_tools import search_web, read_and_summarize_url
from memory_engine import (
    get_memory_stats,
    add_memory,
    delete_memory,
    add_custom_trigger,
    delete_custom_trigger,
)
from free_ai_router import get_free_pool_status
from remote_bridge import (
    push_mobile_notification,
    get_mobile_notifications,
    get_remote_connection_info,
    start_public_internet_tunnel,
    start_cloud_relay_listener,
)
from terminal_manager import (
    get_or_init_terminal_session,
    execute_terminal_command,
    is_direct_shell_command,
)
from automation_engine import (
    start_automation_and_clipboard_daemons,
    run_automation_by_id,
    get_os_clipboard,
    set_os_clipboard,
    start_pomodoro,
    stop_pomodoro,
    get_pomodoro_status,
)
from ai_engine import process_chat_message
from terminal_manager import sync_all_terminal_cwds, set_terminal_cwd
from project_builder import PROJECTS_ROOT
from system_optimizer import (
    scan_updatable_apps,
    upgrade_apps,
    start_upgrade_apps_async,
    get_optimizer_job_status,
    scan_drivers_and_firmware,
    trigger_driver_update_scan,
    run_pc_optimization,
)
from updater import (
    get_update_status,
    check_for_updates,
    apply_update,
    start_auto_update_daemon,
    build_portable_app_zip,
)
from packs_manager import (
    list_packs,
    toggle_pack,
    run_pack_action,
    get_weather,
    get_finance_quotes,
    get_tech_news,
    translate_text,
    run_dev_util,
    get_daily_briefing,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_cloud_relay_listener()
    start_public_internet_tunnel()
    start_automation_and_clipboard_daemons()
    start_auto_update_daemon()
    yield


app = FastAPI(title="AURA OS 5.0 — Ultimate Edition", version="5.0.0", lifespan=lifespan)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

_HUD_DISPATCHER = None


def register_hud_dispatcher(fn):
    global _HUD_DISPATCHER
    _HUD_DISPATCHER = fn


# --- Pydantic Models ---
class HudControlRequest(BaseModel):
    action: str = "toggle"


class ChatRequest(BaseModel):
    message: str
    preferred_model: Optional[str] = None


class AppActionRequest(BaseModel):
    target: str


class MediaActionRequest(BaseModel):
    action: str


class PowerActionRequest(BaseModel):
    action: str
    delay_minutes: int = 30


class RoutineRequest(BaseModel):
    routine_id: str


class AutostartRequest(BaseModel):
    enable: bool


class TaskCreateRequest(BaseModel):
    title: str
    category: str = "Geral"
    priority: str = "media"
    due_time: str = ""


class NoteCreateRequest(BaseModel):
    title: str
    content: str


class AutomationCreateRequest(BaseModel):
    name: str
    schedule_type: str = "interval"
    schedule_value: str = "60"
    action_type: str = "ai_prompt"
    action_payload: str


class ClipboardSetRequest(BaseModel):
    text: str


class ClipboardAiRequest(BaseModel):
    task: str = "resumir"
    text: str = ""


class PomodoroStartRequest(BaseModel):
    minutes: int = 25
    label: str = "Sessão de Foco"


class MemoryFactRequest(BaseModel):
    category: str = "Preferência"
    fact: str


class MemoryTriggerRequest(BaseModel):
    phrase: str
    action_command: str


class CanvasSaveRequest(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]


class CanvasTemplateRequest(BaseModel):
    template_key: str


class CanvasRunAgentRequest(BaseModel):
    node_id: str
    agent_name: str
    agent_role: str
    model_id: str = "free:openai"
    prompt: str
    terminal_cmd: str = ""
    upstream_outputs: List[Dict[str, str]] = []


class TerminalExecRequest(BaseModel):
    node_id: str
    command: str
    node_name: str = "Terminal AURA"
    notify_mobile: bool = False


class TerminalAgentInputRequest(BaseModel):
    node_id: str
    raw_input: str
    agent_name: str = "Assistente AURA"
    agent_role: str = "Agente Autônomo de Terminal"
    model_id: str = "free:openai"
    mode: str = "auto"  # 'auto', 'prompt', 'shell'
    upstream_outputs: List[Dict[str, str]] = []


class CustomAppSyncRequest(BaseModel):
    name: str
    target_path: str
    category: str = "Personalizado"
    icon: str = "app-window"


class WebSearchRequest(BaseModel):
    query: str


class UrlReadRequest(BaseModel):
    url: str


class FileSearchRequest(BaseModel):
    query: str = ""
    folder: str = "downloads"


class OrganizeFolderRequest(BaseModel):
    folder: str = "downloads"
    dry_run: bool = True


class SettingsUpdateRequest(BaseModel):
    assistant_name: Optional[str] = None
    response_style: Optional[str] = None
    custom_system_prompt: Optional[str] = None
    ai_provider: Optional[str] = None
    default_free_model: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    groq_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None
    voice_reply: Optional[bool] = None
    voice_rate: Optional[float] = None
    auto_learn_memory: Optional[bool] = None
    terminal_input_mode: Optional[str] = None
    agent_auto_exec_shell: Optional[bool] = None
    default_terminal_cwd: Optional[str] = None
    terminal_timeout_sec: Optional[int] = None
    hud_compact_w: Optional[int] = None
    hud_expanded_w: Optional[int] = None
    hud_expanded_h: Optional[int] = None
    notify_on_tasks: Optional[bool] = None
    notify_on_terminal: Optional[bool] = None
    notify_on_chat: Optional[bool] = None
    hardware_alert_threshold: Optional[int] = None
    cloud_channel_id: Optional[str] = None
    auto_update_enabled: Optional[bool] = None
    update_repo: Optional[str] = None
    update_branch: Optional[str] = None
    update_check_interval_sec: Optional[int] = None
    auto_restart_on_update: Optional[bool] = None
    remote_pin: Optional[str] = None
    active_workspace: Optional[str] = None
    global_env_vars: Optional[Dict[str, str]] = None
    cerebras_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    custom_openai_url: Optional[str] = None
    custom_openai_key: Optional[str] = None
    custom_openai_model: Optional[str] = None
    enabled_packs: Optional[Dict[str, bool]] = None


class PackToggleRequest(BaseModel):
    enabled: Optional[bool] = None


class PackRunRequest(BaseModel):
    action: str = ""
    params: Dict[str, Any] = {}


class TranslateRequest(BaseModel):
    text: str
    target_lang: str = "en"
    source_lang: str = "pt"


class DevUtilRequest(BaseModel):
    action: str
    params: Dict[str, Any] = {}


class WebhookTriggerRequest(BaseModel):
    event: str = "chat"
    payload: Dict[str, Any] = {}
    notify_mobile: bool = True


class WorkspaceSetRequest(BaseModel):
    path: str


class WorkspaceRevertRequest(BaseModel):
    file_path: str


class WorkspaceCommitRequest(BaseModel):
    message: str
    push: bool = False


class PlaybookSaveRequest(BaseModel):
    name: str
    content: str


class AutoRunStartRequest(BaseModel):
    mode: str = "spec"
    playbook_name: str = ""
    goal: str = ""
    model_id: str = "free:qwen-coder"
    max_iters: int = 4


class WorktreeCreateRequest(BaseModel):
    branch: str
    node_id: str = ""


class WorktreeRemoveRequest(BaseModel):
    worktree_path: str


class OptimizerRunRequest(BaseModel):
    tasks: Optional[List[str]] = None


class AppUpgradeRequest(BaseModel):
    app_ids: Optional[List[str]] = None
    background: bool = True


@app.middleware("http")
async def remote_pin_guard(request: Request, call_next):
    path = request.url.path
    protected_prefixes = ("/api/terminal/", "/api/optimizer/", "/api/workspace/")
    if path.startswith(protected_prefixes):
        client_host = request.client.host if request.client else ""
        is_local = client_host in ("127.0.0.1", "::1", "localhost", "testclient")
        if not is_local:
            pin = str(get_settings().get("remote_pin") or "").strip()
            if pin:
                provided = request.headers.get("X-AURA-Pin") or request.query_params.get("pin") or ""
                if provided != pin:
                    return JSONResponse(status_code=401, content={"detail": "PIN remoto inválido ou ausente (X-AURA-Pin)."})
    return await call_next(request)


# --- HTML Pages ---
@app.get("/")
def serve_index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/mobile")
def serve_mobile():
    return FileResponse(str(STATIC_DIR / "mobile.html"))


@app.get("/hud")
def serve_hud():
    return FileResponse(str(STATIC_DIR / "hud.html"))


# --- API Endpoints ---
@app.post("/api/chat")
def api_chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Mensagem vazia")
    return process_chat_message(req.message, preferred_model=req.preferred_model)


@app.get("/api/ai/pool")
def api_ai_pool():
    return {"pool": get_free_pool_status()}


@app.get("/api/memory")
def api_get_memory():
    return get_memory_stats()


@app.post("/api/memory/fact")
def api_add_memory_fact(req: MemoryFactRequest):
    return add_memory(req.category, req.fact, source="manual")


@app.delete("/api/memory/fact/{mem_id}")
def api_delete_memory_fact(mem_id: int):
    return {"deleted": delete_memory(mem_id)}


@app.post("/api/memory/trigger")
def api_add_trigger(req: MemoryTriggerRequest):
    return add_custom_trigger(req.phrase, req.action_command)


@app.delete("/api/memory/trigger/{trig_id}")
def api_delete_trigger(trig_id: int):
    return {"deleted": delete_custom_trigger(trig_id)}


@app.get("/api/chat/history")
def api_chat_history(limit: int = 20):
    return {"items": get_chat_history(limit)}


@app.delete("/api/chat/history")
def api_clear_chat_history():
    cleared = clear_chat_history()
    return {"ok": True, "deleted": cleared}


@app.get("/api/workspace/projects")
def api_workspace_projects():
    s = get_settings()
    projects = []
    if PROJECTS_ROOT.exists():
        for p in sorted(PROJECTS_ROOT.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.is_dir():
                projects.append({"name": p.name, "path": str(p)})
    cwd_path = str(Path.cwd())
    if all(pr["path"] != cwd_path for pr in projects):
        projects.insert(0, {"name": f"Workspace Atual ({Path.cwd().name})", "path": cwd_path})
    return {"active": s.get("active_workspace", cwd_path), "projects": projects[:30]}


@app.post("/api/workspace/set")
def api_workspace_set(req: WorkspaceSetRequest):
    sync_res = sync_all_terminal_cwds(req.path)
    if not sync_res.get("ok"):
        raise HTTPException(status_code=400, detail=sync_res.get("error", "Diretório inválido"))
    update_settings({"active_workspace": sync_res["cwd"], "default_terminal_cwd": sync_res["cwd"]})
    return sync_res


@app.get("/api/workspace/diff")
def api_workspace_diff():
    ws = get_settings().get("active_workspace") or str(Path.cwd())
    flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
    try:
        st = subprocess.run(["git", "status", "--short"], cwd=ws, capture_output=True, text=True, timeout=10, creationflags=flags)
        df = subprocess.run(["git", "diff", "--no-color"], cwd=ws, capture_output=True, text=True, timeout=12, creationflags=flags)
        files = []
        for line in (st.stdout or "").splitlines():
            if len(line) >= 4:
                files.append({"status": line[:2].strip(), "file": line[3:].strip()})
        return {"ok": True, "workspace": ws, "files": files, "diff": (df.stdout or "")[:12000]}
    except Exception as exc:
        return {"ok": False, "workspace": ws, "files": [], "diff": "", "error": str(exc)}


@app.post("/api/workspace/revert")
def api_workspace_revert(req: WorkspaceRevertRequest):
    ws = get_settings().get("active_workspace") or str(Path.cwd())
    flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
    try:
        res = subprocess.run(["git", "checkout", "--", req.file_path], cwd=ws, capture_output=True, text=True, timeout=10, creationflags=flags)
        return {"ok": res.returncode == 0, "message": res.stderr.strip() or f"Arquivo '{req.file_path}' revertido."}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


@app.post("/api/workspace/commit")
def api_workspace_commit(req: WorkspaceCommitRequest):
    msg = (req.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Mensagem de commit obrigatória.")
    ws = get_settings().get("active_workspace") or str(Path.cwd())
    flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
    try:
        add_res = subprocess.run(["git", "add", "-A"], cwd=ws, capture_output=True, text=True, timeout=15, creationflags=flags)
        if add_res.returncode != 0:
            return {"ok": False, "message": add_res.stderr.strip() or "Falha no git add."}
        cm_res = subprocess.run(["git", "commit", "-m", msg], cwd=ws, capture_output=True, text=True, timeout=15, creationflags=flags)
        if cm_res.returncode != 0:
            return {"ok": False, "message": (cm_res.stderr or cm_res.stdout).strip() or "Falha no git commit."}
        out = (cm_res.stdout or "Commit realizado.").strip()
        if req.push:
            push_res = subprocess.run(["git", "push"], cwd=ws, capture_output=True, text=True, timeout=30, creationflags=flags)
            if push_res.returncode != 0:
                return {"ok": False, "message": f"Commit ok, mas falha no push: {(push_res.stderr or push_res.stdout).strip()}"}
            out += f"\nPush concluído: {(push_res.stdout or push_res.stderr).strip()}"
        log_activity("WORKSPACE", f"Git commit{' + push' if req.push else ''}: {msg[:80]}")
        return {"ok": True, "message": out}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


@app.get("/api/optimizer/apps")
def api_optimizer_apps():
    return scan_updatable_apps()


@app.get("/api/optimizer/status")
def api_optimizer_status():
    return get_optimizer_job_status()


@app.post("/api/optimizer/apps/upgrade")
def api_optimizer_apps_upgrade(req: AppUpgradeRequest):
    if req.background:
        return start_upgrade_apps_async(req.app_ids)
    return upgrade_apps(req.app_ids)


@app.get("/api/optimizer/drivers")
def api_optimizer_drivers():
    return scan_drivers_and_firmware()


@app.post("/api/optimizer/drivers/scan")
def api_optimizer_drivers_scan():
    return trigger_driver_update_scan()


@app.post("/api/optimizer/run")
def api_optimizer_run(req: OptimizerRunRequest):
    return run_pc_optimization(req.tasks)


# --- Gerenciador de Processos do Sistema ---
@app.get("/api/system/processes")
def api_system_processes(limit: int = 25, sort: str = "cpu"):
    return {"processes": get_top_processes(limit=limit, sort_by=sort)}


@app.post("/api/system/processes/{pid}/kill")
def api_kill_process(pid: int):
    return kill_process_by_pid(pid)


# --- Terminal (Unified Shell Execution) ---
@app.get("/api/terminal/{node_id}")
def api_get_terminal(node_id: str):
    return get_or_init_terminal_session(node_id)


@app.post("/api/terminal/exec")
def api_exec_terminal(req: TerminalExecRequest):
    return execute_terminal_command(
        node_id=req.node_id,
        command=req.command,
        notify_mobile=req.notify_mobile,
        node_name=req.node_name,
    )


@app.post("/api/terminal/input")
def api_terminal_agent_input(req: TerminalAgentInputRequest):
    """
    Unified AURA Terminal Handler:
    - If input is a direct shell command (or mode == 'shell'), executes in PowerShell/Bash.
    - Otherwise, executes as the AI Agent's Prompt directly inside the terminal, logging all
      working steps and the final result into the terminal screen!
    """
    text = req.raw_input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Entrada vazia")

    s = get_settings()
    cfg_mode = req.mode if req.mode != "auto" else s.get("terminal_input_mode", "agent_and_shell")

    run_as_shell = False
    if cfg_mode == "shell_only" or req.mode == "shell":
        run_as_shell = True
    elif cfg_mode == "agent_and_shell" and is_direct_shell_command(text):
        run_as_shell = True

    if run_as_shell:
        res = execute_terminal_command(
            node_id=req.node_id,
            command=text,
            notify_mobile=True,
            node_name=req.agent_name,
        )
        last = res.get("last_entry") or {}
        return {
            "execution_type": "shell",
            "output": last.get("output", ""),
            "provider_used": "OS Shell",
            "terminal_session": res["session"],
        }
    else:
        chat_res = process_chat_message(text)
        return {
            "execution_type": "ai_prompt",
            "output": chat_res.get("reply", ""),
            "provider_used": chat_res.get("provider_used", "AURA AI"),
        }


# --- Automations & Cron ---
@app.get("/api/automations")
def api_list_automations():
    return {"automations": list_automations()}


@app.post("/api/automations")
def api_create_automation(req: AutomationCreateRequest):
    return add_automation(
        name=req.name,
        schedule_type=req.schedule_type,
        schedule_value=req.schedule_value,
        action_type=req.action_type,
        action_payload=req.action_payload,
    )


@app.post("/api/automations/{auto_id}/toggle")
def api_toggle_automation(auto_id: int):
    updated = toggle_automation(auto_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Automação não encontrada")
    return updated


@app.post("/api/automations/{auto_id}/run")
def api_run_automation(auto_id: int):
    return run_automation_by_id(auto_id)


@app.delete("/api/automations/{auto_id}")
def api_delete_automation(auto_id: int):
    return {"deleted": delete_automation(auto_id)}


# --- Smart Clipboard & Sync ---
@app.get("/api/clipboard")
def api_get_clipboard():
    current = get_os_clipboard()
    return {
        "current": current[:2000],
        "history": list_clipboard_history(25),
    }


@app.post("/api/clipboard/copy")
def api_set_clipboard(req: ClipboardSetRequest):
    ok = set_os_clipboard(req.text)
    return {
        "success": ok,
        "message": "Texto enviado para a Área de Transferência (Ctrl+V) do PC!" if ok else "Erro ao copiar texto.",
        "history": list_clipboard_history(25),
    }


@app.post("/api/clipboard/ai")
def api_clipboard_ai(req: ClipboardAiRequest):
    text = req.text.strip() or get_os_clipboard().strip()
    if not text:
        return {"reply": "A área de transferência está vazia no momento.", "provider": "Sistema"}
    prompts = {
        "resumir": f"Resuma de forma clara e em tópicos o seguinte texto copiado:\n\n{text[:3000]}",
        "explicar": f"Explique de forma didática o seguinte código ou texto copiado:\n\n{text[:3000]}",
        "traduzir": f"Traduza para Português do Brasil (ou para Inglês se já estiver em Português) o seguinte texto:\n\n{text[:3000]}",
        "melhorar": f"Melhore a escrita, clareza ou refatore o seguinte código/texto:\n\n{text[:3000]}",
    }
    p = prompts.get(req.task, prompts["resumir"])
    return process_chat_message(p)


@app.post("/api/clipboard/{clip_id}/pin")
def api_pin_clipboard(clip_id: int):
    return toggle_pin_clipboard(clip_id) or {}


@app.delete("/api/clipboard/{clip_id}")
def api_delete_clipboard(clip_id: int):
    return {"deleted": delete_clipboard_item(clip_id)}


# --- Pomodoro & Deep Focus Timer ---
@app.get("/api/pomodoro")
def api_get_pomodoro():
    return get_pomodoro_status()


@app.post("/api/pomodoro/start")
def api_start_pomodoro(req: PomodoroStartRequest):
    return start_pomodoro(req.minutes, req.label)


@app.post("/api/pomodoro/stop")
def api_stop_pomodoro():
    return stop_pomodoro()


# --- Remote & Mobile Notifications ---
@app.get("/api/remote/info")
def api_remote_info():
    return get_remote_connection_info()


@app.post("/api/remote/start-tunnel")
def api_start_tunnel():
    return start_public_internet_tunnel()


@app.get("/api/mobile/notifications")
def api_mobile_notifications(since_id: int = 0):
    return {"notifications": get_mobile_notifications(since_id)}


@app.post("/api/mobile/test-notification")
def api_test_mobile_notification():
    return push_mobile_notification(
        title="Teste de Notificação AURA 5.0",
        body="A AURA OS concluiu uma tarefa e notificou seu celular em tempo real!",
        category="TESTE",
        agent_name="AURA",
    )


# --- System & Hardware ---
@app.get("/api/system/stats")
def api_system_stats():
    stats = get_system_stats()
    stats["remote"] = get_remote_connection_info()
    stats["pomodoro"] = get_pomodoro_status()
    return stats


@app.get("/api/system/network-diag")
def api_network_diag():
    return get_network_diagnostics()


@app.post("/api/system/power")
def api_power_control(req: PowerActionRequest):
    return power_control(req.action, req.delay_minutes)


@app.get("/api/system/apps")
def api_system_apps():
    return {"apps": get_quick_apps_catalog()}


@app.post("/api/system/apps/sync")
def api_sync_apps():
    return sync_installed_apps()


@app.post("/api/system/apps/custom")
def api_add_custom_app(req: CustomAppSyncRequest):
    app_id = req.name.lower().strip().replace(" ", "_")
    save_synced_apps_batch(
        [
            {
                "id": app_id,
                "name": req.name.strip(),
                "target_path": req.target_path.strip(),
                "exe_name": Path(req.target_path.strip()).name.lower(),
                "category": req.category.strip() or "Personalizado",
                "icon": req.icon.strip() or "app-window",
                "source": "manual",
            }
        ]
    )
    return {"success": True, "apps": get_quick_apps_catalog(), "message": f"Aplicativo **{req.name}** adicionado e sincronizado!"}


@app.delete("/api/system/apps/{app_id}")
def api_delete_synced_app(app_id: str):
    return {"deleted": delete_synced_app(app_id), "apps": get_quick_apps_catalog()}


@app.post("/api/system/open")
def api_open_app(req: AppActionRequest):
    return open_application(req.target)


@app.post("/api/system/close")
def api_close_app(req: AppActionRequest):
    return close_application(req.target)


@app.post("/api/system/screenshot")
def api_screenshot():
    return take_screenshot(open_after=False)


@app.get("/api/system/screenshot-file/{filename}")
def api_get_screenshot_file(filename: str):
    safe_name = Path(filename).name
    target = Path.home() / "Pictures" / "Capturas_AURA" / safe_name
    if not target.exists():
        raise HTTPException(status_code=404, detail="Captura não encontrada")
    return FileResponse(str(target))


@app.post("/api/system/media")
def api_media(req: MediaActionRequest):
    return media_and_volume_control(req.action)


@app.post("/api/system/clean-temp")
def api_clean_temp():
    return clean_temp_files()


@app.post("/api/system/empty-trash")
def api_empty_trash():
    return empty_recycle_bin()


@app.post("/api/system/lock")
def api_lock():
    return lock_workstation()


@app.post("/api/system/routine")
def api_routine(req: RoutineRequest):
    return run_productivity_routine(req.routine_id)


@app.get("/api/system/background-status")
def api_bg_status():
    return get_background_status()


@app.post("/api/system/autostart")
def api_autostart(req: AutostartRequest):
    return toggle_windows_autostart(req.enable)


@app.post("/api/system/desktop-shortcut")
def api_desktop_shortcut():
    return create_desktop_launcher()


@app.post("/api/hud/control")
def api_hud_control(req: HudControlRequest):
    if _HUD_DISPATCHER is not None:
        return _HUD_DISPATCHER(req.action)
    return {"ok": False, "active": False}


@app.get("/api/hud/state")
def api_get_hud_state():
    from datetime import datetime
    s = get_settings()
    today = datetime.now().strftime("%Y-%m-%d")
    habits = s.get("hud_habits") or {"date": today, "water": 0, "read": 0, "exercise": 0}
    if not isinstance(habits, dict) or habits.get("date") != today:
        habits = {"date": today, "water": 0, "read": 0, "exercise": 0}
        update_settings({"hud_habits": habits})
    mascot = s.get("hud_mascot") or {
        "name": s.get("assistant_name", "AURA"),
        "body": "#F4F7FF",
        "body2": "#BFCDF5",
        "visor": "#1B1E2B",
        "eye": "#9BF35A",
        "eyeStyle": "round",
        "accessory": "none",
        "silentMode": False,
        "voiceSpeak": True,
    }
    return {"habits": habits, "mascot": mascot}


@app.post("/api/hud/state")
async def api_save_hud_state(request: Request):
    from datetime import datetime
    body = await request.json()
    updates = {}
    if "habits" in body and isinstance(body["habits"], dict):
        h = dict(body["habits"])
        h["date"] = datetime.now().strftime("%Y-%m-%d")
        updates["hud_habits"] = h
    if "mascot" in body and isinstance(body["mascot"], dict):
        updates["hud_mascot"] = body["mascot"]
        if body["mascot"].get("name"):
            updates["assistant_name"] = str(body["mascot"]["name"])[:24]
    if updates:
        update_settings(updates)
    return api_get_hud_state()


@app.post("/api/system/launch-hud")
def api_launch_hud():
    if _HUD_DISPATCHER is not None:
        res = _HUD_DISPATCHER("expand")
        if res.get("active"):
            return {"success": True, "message": "Painel Superior CSS exibido e expandido no topo da tela!"}
    widget_path = Path(__file__).parent / "desktop_widget.py"
    if IS_WINDOWS:
        pythonw = Path(sys.executable).parent / "pythonw.exe"
        exe = str(pythonw) if pythonw.exists() else sys.executable
    else:
        exe = sys.executable
    try:
        subprocess.Popen([exe, str(widget_path)], cwd=str(Path(__file__).parent))
        return {"success": True, "message": "Painel Superior CSS (Dynamic Island) iniciado!"}
    except Exception as e:
        return {"success": False, "message": f"Erro ao iniciar HUD: {e}"}


# --- Tasks, Notes, Web & Files ---
@app.get("/api/tasks")
def api_get_tasks():
    return {"tasks": list_tasks(include_done=True)}


@app.post("/api/tasks")
def api_create_task(req: TaskCreateRequest):
    return add_task(req.title, req.category, req.priority, req.due_time)


@app.post("/api/tasks/{task_id}/toggle")
def api_toggle_task(task_id: int):
    updated = toggle_task(task_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return updated


@app.delete("/api/tasks/{task_id}")
def api_delete_task(task_id: int):
    ok = delete_task(task_id)
    return {"deleted": ok}


@app.get("/api/notes")
def api_get_notes():
    return {"notes": list_notes()}


@app.post("/api/notes")
def api_create_note(req: NoteCreateRequest):
    return add_note(req.title, req.content)


@app.delete("/api/notes/{note_id}")
def api_delete_note(note_id: int):
    return {"deleted": delete_note(note_id)}


@app.post("/api/web/search")
def api_web_search(req: WebSearchRequest):
    return search_web(req.query)


@app.post("/api/web/read")
def api_web_read(req: UrlReadRequest):
    return read_and_summarize_url(req.url)


@app.post("/api/files/search")
def api_files_search(req: FileSearchRequest):
    return search_local_files(req.query, req.folder)


@app.post("/api/files/organize")
def api_files_organize(req: OrganizeFolderRequest):
    return organize_directory(req.folder, req.dry_run)


@app.get("/api/logs")
def api_logs():
    return {"logs": get_recent_logs(30)}


@app.get("/api/settings")
def api_get_settings():
    return get_settings()


@app.post("/api/settings")
def api_save_settings(req: SettingsUpdateRequest):
    payload = {k: v for k, v in req.model_dump().items() if v is not None}
    return update_settings(payload)


@app.post("/api/settings/clear-logs")
def api_clear_logs():
    removed = clear_activity_logs()
    return {"success": True, "removed": removed, "message": "Histórico de logs limpo com sucesso!"}


# --- App Download & Auto-Update (main) ---
@app.get("/api/updates/status")
def api_updates_status():
    return get_update_status()


@app.post("/api/updates/check")
def api_updates_check():
    return check_for_updates()


@app.post("/api/updates/apply")
def api_updates_apply():
    return apply_update(restart=True)


@app.get("/api/updates/download-installer")
def api_download_installer():
    installer_path = Path(__file__).parent / "Instalar_AURA.bat"
    if not installer_path.exists():
        raise HTTPException(status_code=404, detail="Instalador Instalar_AURA.bat não encontrado.")
    return FileResponse(
        path=str(installer_path),
        media_type="application/octet-stream",
        filename="Instalar_AURA.bat",
    )


@app.get("/api/updates/download-bundle")
def api_download_bundle():
    zip_bytes = build_portable_app_zip()
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="AURA-OS-App.zip"'},
    )


# --- Packs, External APIs, Webhooks & Extended System Endpoints ---
@app.get("/api/capabilities")
def api_capabilities():
    return {
        "name": "AURA OS",
        "version": "5.1.0",
        "docs_url": "/docs",
        "openapi_url": "/openapi.json",
        "packs": list_packs(),
        "ai_pool": get_free_pool_status(),
        "endpoints": {
            "chat": "POST /api/chat",
            "packs_list": "GET /api/packs",
            "packs_run": "POST /api/packs/{pack_id}/run",
            "weather": "GET /api/packs/weather?city=Sao+Paulo",
            "finance": "GET /api/packs/finance?pairs=USD-BRL,EUR-BRL,BTC-BRL",
            "news": "GET /api/packs/news?topic=pt&limit=6",
            "translate": "POST /api/packs/translate",
            "dev_utils": "POST /api/packs/dev-utils",
            "briefing": "GET /api/packs/briefing?city=Sao+Paulo",
            "ports": "GET /api/system/ports",
            "dev_env": "GET /api/system/dev-env",
            "backup": "GET /api/system/backup",
            "webhook": "POST /api/webhooks/trigger",
        },
    }


@app.get("/api/packs")
def api_list_packs():
    return {"packs": list_packs()}


@app.post("/api/packs/{pack_id}/toggle")
def api_toggle_pack(pack_id: str, req: Optional[PackToggleRequest] = None):
    enabled = req.enabled if req else None
    res = toggle_pack(pack_id, enabled=enabled)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error", "Pack não encontrado"))
    return res


@app.post("/api/packs/{pack_id}/run")
def api_run_pack(pack_id: str, req: PackRunRequest):
    return run_pack_action(pack_id=pack_id, action=req.action, params=req.params)


@app.get("/api/packs/weather")
def api_pack_weather(city: str = "São Paulo"):
    return run_pack_action("weather", "forecast", {"city": city})


@app.get("/api/packs/finance")
def api_pack_finance(pairs: str = "USD-BRL,EUR-BRL,BTC-BRL,ETH-BRL"):
    return run_pack_action("finance", "quotes", {"pairs": pairs})


@app.get("/api/packs/news")
def api_pack_news(topic: str = "pt", limit: int = 6):
    return run_pack_action("news", "headlines", {"topic": topic, "limit": limit})


@app.post("/api/packs/translate")
def api_pack_translate(req: TranslateRequest):
    return run_pack_action(
        "translate",
        "translate",
        {"text": req.text, "target_lang": req.target_lang, "source_lang": req.source_lang},
    )


@app.post("/api/packs/dev-utils")
def api_pack_dev_utils(req: DevUtilRequest):
    return run_pack_action("dev_utils", req.action, req.params)


@app.get("/api/packs/briefing")
def api_pack_briefing(city: str = "São Paulo"):
    return run_pack_action("productivity", "daily_briefing", {"city": city})


@app.get("/api/system/ports")
def api_system_ports(limit: int = 35):
    ports = get_open_ports(limit=limit)
    return {"ports": ports, "count": len(ports)}


@app.get("/api/system/dev-env")
def api_system_dev_env():
    return get_dev_environment_info()


@app.get("/api/system/backup")
def api_system_backup():
    data = export_all_data()
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": 'attachment; filename="aura-backup.json"'},
    )


@app.post("/api/webhooks/trigger")
def api_webhook_trigger(req: WebhookTriggerRequest):
    ev = (req.event or "chat").lower().strip()
    p = req.payload or {}
    if ev == "chat":
        msg = str(p.get("message", "")).strip()
        if not msg:
            raise HTTPException(status_code=400, detail="Campo payload.message é obrigatório.")
        result = process_chat_message(msg, preferred_model=p.get("preferred_model"))
        if req.notify_mobile:
            push_mobile_notification("Webhook Chat", result.get("reply", "")[:200], category="WEBHOOK")
        return {"ok": True, "event": ev, "result": result}
    if ev == "pack":
        pack_id = str(p.get("pack_id", ""))
        action = str(p.get("action", ""))
        params = p.get("params") if isinstance(p.get("params"), dict) else {}
        return {"ok": True, "event": ev, "result": run_pack_action(pack_id, action, params)}
    if ev == "notify":
        title = str(p.get("title", "Alerta Webhook"))
        body = str(p.get("body", "Evento recebido pela API AURA."))
        push_mobile_notification(title, body, category="WEBHOOK")
        return {"ok": True, "event": ev, "notified": True}
    raise HTTPException(status_code=400, detail=f"Evento webhook '{ev}' não suportado (use chat, pack ou notify).")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn

    print("==========================================================")
    print("  AURA OS - Assistente Pessoal de Computador com IA")
    print("  Painel Local: http://localhost:8765")
    print("==========================================================")
    uvicorn.run(app, host="0.0.0.0", port=8765)

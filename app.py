import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
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
    get_canvas_state,
    save_canvas_state,
    get_maestri_templates,
    load_maestri_template,
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
)
from system_tools import (
    get_system_stats,
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
    export_maestri_report,
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
from ai_engine import process_chat_message, run_maestri_canvas_agent
from maestri_orchestrator import (
    ipc_check,
    ipc_ask,
    ipc_spawn,
    run_maestro_mode,
    detect_installed_clis,
    detect_runmaestro,
    launch_or_open_runmaestro,
)
from updater import (
    get_update_status,
    check_for_updates,
    apply_update,
    start_auto_update_daemon,
    build_portable_app_zip,
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
    node_name: str = "Terminal Maestri"
    notify_mobile: bool = False


class TerminalAgentInputRequest(BaseModel):
    node_id: str
    raw_input: str
    agent_name: str = "Agente Maestri"
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
    notify_on_maestri: Optional[bool] = None
    notify_on_terminal: Optional[bool] = None
    notify_on_chat: Optional[bool] = None
    hardware_alert_threshold: Optional[int] = None
    cloud_channel_id: Optional[str] = None
    auto_update_enabled: Optional[bool] = None
    update_repo: Optional[str] = None
    update_branch: Optional[str] = None
    update_check_interval_sec: Optional[int] = None
    auto_restart_on_update: Optional[bool] = None


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


# --- Maestri 2D Canvas & Templates ---
@app.get("/api/canvas")
def api_get_canvas():
    state = get_canvas_state()
    for n in state.get("nodes", []):
        sess = get_or_init_terminal_session(n["id"], n.get("cwd", ""))
        n["terminal"] = sess
    return state


@app.post("/api/canvas/save")
def api_save_canvas(req: CanvasSaveRequest):
    return save_canvas_state(req.nodes, req.edges)


@app.get("/api/canvas/templates")
def api_get_canvas_templates():
    tpls = get_maestri_templates()
    return {
        "templates": [
            {"key": k, "name": v["name"], "description": v["description"], "node_count": len(v["nodes"])}
            for k, v in tpls.items()
        ]
    }


@app.post("/api/canvas/load-template")
def api_load_canvas_template(req: CanvasTemplateRequest):
    state = load_maestri_template(req.template_key)
    for n in state.get("nodes", []):
        n["terminal"] = get_or_init_terminal_session(n["id"], n.get("cwd", ""))
    return state


@app.post("/api/canvas/export")
def api_export_canvas():
    state = get_canvas_state()
    return export_maestri_report(state.get("nodes", []))


@app.post("/api/canvas/run-agent")
def api_run_canvas_agent(req: CanvasRunAgentRequest):
    return run_maestri_canvas_agent(
        node_id=req.node_id,
        agent_name=req.agent_name,
        agent_role=req.agent_role,
        model_id=req.model_id,
        prompt=req.prompt,
        terminal_cmd=req.terminal_cmd,
        upstream_outputs=req.upstream_outputs,
    )


class MaestroGoalRequest(BaseModel):
    goal: str


class IpcAskRequest(BaseModel):
    target: str
    prompt: str


class IpcSpawnRequest(BaseModel):
    name: str
    role: str
    prompt: str = ""
    model: str = "free:openai"


@app.post("/api/canvas/maestro-run")
def api_canvas_maestro_run(req: MaestroGoalRequest):
    return run_maestro_mode(req.goal)


@app.get("/api/canvas/ipc/check")
def api_canvas_ipc_check():
    return ipc_check()


@app.post("/api/canvas/ipc/ask")
def api_canvas_ipc_ask(req: IpcAskRequest):
    return ipc_ask(req.target, req.prompt)


@app.post("/api/canvas/ipc/spawn")
def api_canvas_ipc_spawn(req: IpcSpawnRequest):
    return ipc_spawn(req.name, req.role, req.prompt, req.model)


@app.get("/api/maestri/clis")
def api_maestri_clis():
    return {
        "clis": detect_installed_clis(),
        "runmaestro": detect_runmaestro(),
    }


@app.post("/api/maestri/runmaestro/launch")
def api_launch_runmaestro():
    return launch_or_open_runmaestro()


# --- Terminal (Unified Agent Prompt + Shell Execution) ---
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
    Unified Maestri Terminal Handler:
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
        res = run_maestri_canvas_agent(
            node_id=req.node_id,
            agent_name=req.agent_name,
            agent_role=req.agent_role,
            model_id=req.model_id,
            prompt=text,
            terminal_cmd="",
            upstream_outputs=req.upstream_outputs,
        )
        res["execution_type"] = "agent_prompt"
        return res


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
        body="O Maestri ou Agente IA concluiu uma tarefa e notificou seu celular em tempo real!",
        category="TESTE",
        agent_name="Maestro",
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


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn

    print("==========================================================")
    print("  AURA OS 5.0 - Ultimate Maestri & Automation Suite")
    print("  Painel Local: http://localhost:8765")
    print("==========================================================")
    uvicorn.run(app, host="0.0.0.0", port=8765)

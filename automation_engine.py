import time
import threading
import subprocess
from datetime import datetime
from typing import Dict, Any, Optional

from storage import (
    list_automations,
    record_automation_run,
    save_clipboard_item,
    list_clipboard_history,
    log_activity,
)
from system_tools import IS_WINDOWS, get_system_stats, run_productivity_routine
from remote_bridge import push_mobile_notification
from terminal_manager import execute_terminal_command

_AUTOMATION_DAEMON_STARTED = False
_LAST_RUN_TS: Dict[int, float] = {}
_LAST_DAILY_DATE: Dict[int, str] = {}

_POMODORO_STATE: Dict[str, Any] = {
    "active": False,
    "label": "Foco Pomodoro",
    "duration_sec": 1500,
    "end_ts": 0.0,
    "completed_sessions": 0,
}


# --- Cross-Platform OS Clipboard Access (Windows Win32 + Linux Ubuntu) ---
def get_os_clipboard() -> str:
    if IS_WINDOWS:
        try:
            import ctypes
            CF_UNICODETEXT = 13
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            user32.OpenClipboard.argtypes = [ctypes.c_void_p]
            user32.GetClipboardData.restype = ctypes.c_void_p
            kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalLock.restype = ctypes.c_wchar_p
            kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

            if not user32.OpenClipboard(None):
                return ""
            try:
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return ""
                pcontents = kernel32.GlobalLock(handle)
                data = pcontents if pcontents else ""
                kernel32.GlobalUnlock(handle)
                return data
            finally:
                user32.CloseClipboard()
        except Exception:
            return ""
    else:
        for cmd in (["wl-paste", "-n"], ["xclip", "-selection", "clipboard", "-o"], ["xsel", "-ob"]):
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
                if res.returncode == 0:
                    return res.stdout
            except Exception:
                continue
        return ""


def set_os_clipboard(text: str) -> bool:
    clean = str(text or "")
    if IS_WINDOWS:
        try:
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $input"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            proc.communicate(input=clean, timeout=3)
            save_clipboard_item(clean)
            return True
        except Exception:
            return False
    else:
        for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-ib"]):
            try:
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, text=True)
                proc.communicate(input=clean, timeout=2)
                save_clipboard_item(clean)
                return True
            except Exception:
                continue
        return False


# --- Synchronized Pomodoro & Deep Focus Timer ---
def start_pomodoro(minutes: int = 25, label: str = "Sessão de Foco") -> Dict[str, Any]:
    mins = max(1, min(int(minutes), 180))
    _POMODORO_STATE["active"] = True
    _POMODORO_STATE["label"] = label.strip() or "Sessão de Foco"
    _POMODORO_STATE["duration_sec"] = mins * 60
    _POMODORO_STATE["end_ts"] = time.time() + (mins * 60)
    log_activity("POMODORO", f"Timer iniciado: {_POMODORO_STATE['label']} ({mins} min)")
    return get_pomodoro_status()


def stop_pomodoro() -> Dict[str, Any]:
    _POMODORO_STATE["active"] = False
    _POMODORO_STATE["end_ts"] = 0.0
    log_activity("POMODORO", "Timer de foco encerrado")
    return get_pomodoro_status()


def get_pomodoro_status() -> Dict[str, Any]:
    if _POMODORO_STATE["active"]:
        rem = int(round(_POMODORO_STATE["end_ts"] - time.time()))
        if rem <= 0:
            _POMODORO_STATE["active"] = False
            _POMODORO_STATE["end_ts"] = 0.0
            _POMODORO_STATE["completed_sessions"] += 1
            push_mobile_notification(
                title=f"Timer Concluído: {_POMODORO_STATE['label']}",
                body=f"Sua sessão de foco ({_POMODORO_STATE['duration_sec'] // 60} min) terminou! Hora de fazer uma pausa.",
                category="POMODORO",
                agent_name="AURA Timer",
            )
            log_activity("POMODORO", f"Concluído: {_POMODORO_STATE['label']}")
            rem = 0
        mm = rem // 60
        ss = rem % 60
        formatted = f"{mm:02d}:{ss:02d}"
    else:
        rem = 0
        formatted = "00:00"

    return {
        "active": _POMODORO_STATE["active"],
        "label": _POMODORO_STATE["label"],
        "remaining_sec": rem,
        "duration_sec": _POMODORO_STATE["duration_sec"],
        "formatted": formatted,
        "completed_sessions": _POMODORO_STATE["completed_sessions"],
    }


# --- Automation Execution Engine ---
def execute_automation_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    auto_id = rule["id"]
    name = rule["name"]
    act_type = rule["action_type"]
    payload = rule["action_payload"]
    result_summary = ""

    try:
        if act_type == "routine":
            res = run_productivity_routine(payload)
            result_summary = res.get("message", "Rotina executada.")
        elif act_type == "terminal_cmd":
            res = execute_terminal_command(
                node_id=f"auto-{auto_id}",
                command=payload,
                notify_mobile=False,
                node_name=f"Automação: {name}",
            )
            result_summary = res.get("output", "Comando concluído.")[:280]
        elif act_type == "system_alert":
            stats = get_system_stats()
            cpu = stats["cpu"]["percent"]
            ram = stats["ram"]["percent"]
            result_summary = f"Sentinela verificada — CPU: {cpu}% | RAM: {ram}% ({stats['ram']['used_gb']} GB)"
        else:
            # Default: ai_prompt
            from ai_engine import process_chat_message
            res = process_chat_message(payload)
            result_summary = res.get("reply", "Executado pela IA.")[:280]

        record_automation_run(auto_id, result_summary)
        push_mobile_notification(
            title=f"Automação Concluída: {name}",
            body=result_summary,
            category="AUTOMAÇÃO",
            agent_name="AURA Cron",
        )
        return {"success": True, "id": auto_id, "name": name, "result": result_summary}
    except Exception as e:
        err_msg = f"Erro na automação: {e}"
        record_automation_run(auto_id, err_msg)
        return {"success": False, "id": auto_id, "name": name, "result": err_msg}


def run_automation_by_id(auto_id: int) -> Dict[str, Any]:
    for r in list_automations():
        if r["id"] == auto_id:
            return execute_automation_rule(r)
    return {"success": False, "result": "Regra de automação não encontrada."}


def start_automation_and_clipboard_daemons() -> None:
    """Background daemon that monitors OS Clipboard, Pomodoro Timer, and Scheduled Automations."""
    global _AUTOMATION_DAEMON_STARTED
    if _AUTOMATION_DAEMON_STARTED:
        return
    _AUTOMATION_DAEMON_STARTED = True

    def _daemon_loop():
        last_clip = ""
        tick = 0
        while True:
            try:
                # 1. Check Pomodoro completion every 2 seconds
                if _POMODORO_STATE["active"]:
                    get_pomodoro_status()

                # 2. Sample OS Clipboard every 4 seconds
                if tick % 2 == 0:
                    cur_clip = get_os_clipboard().strip()
                    if cur_clip and cur_clip != last_clip:
                        last_clip = cur_clip
                        save_clipboard_item(cur_clip)

                # 3. Check Scheduled Automations every 20 seconds
                if tick % 10 == 0:
                    now_ts = time.time()
                    now_hm = datetime.now().strftime("%H:%M")
                    today_str = datetime.now().strftime("%Y-%m-%d")

                    rules = list_automations()
                    for rule in rules:
                        if not rule.get("enabled"):
                            continue
                        rid = rule["id"]
                        stype = rule["schedule_type"]
                        sval = str(rule["schedule_value"]).strip()

                        if stype == "interval":
                            try:
                                interval_sec = max(1, int(sval)) * 60
                            except Exception:
                                interval_sec = 3600
                            last_t = _LAST_RUN_TS.get(rid, now_ts)
                            if rid not in _LAST_RUN_TS:
                                _LAST_RUN_TS[rid] = now_ts
                            elif now_ts - last_t >= interval_sec:
                                _LAST_RUN_TS[rid] = now_ts
                                execute_automation_rule(rule)

                        elif stype == "daily":
                            if sval == now_hm and _LAST_DAILY_DATE.get(rid) != today_str:
                                _LAST_DAILY_DATE[rid] = today_str
                                execute_automation_rule(rule)

                        elif stype == "threshold":
                            try:
                                limit_pct = float(sval)
                            except Exception:
                                limit_pct = 88.0
                            last_t = _LAST_RUN_TS.get(rid, 0.0)
                            # Cooldown of 10 minutes between threshold alerts
                            if now_ts - last_t >= 600:
                                stats = get_system_stats()
                                if stats["cpu"]["percent"] >= limit_pct or stats["ram"]["percent"] >= limit_pct:
                                    _LAST_RUN_TS[rid] = now_ts
                                    execute_automation_rule(rule)

            except Exception:
                pass

            tick += 1
            time.sleep(2.0)

    threading.Thread(target=_daemon_loop, daemon=True).start()

import os
import time
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
from system_tools import IS_WINDOWS, OS_NAME
from storage import log_activity, get_settings
from remote_bridge import push_mobile_notification

# Per-node terminal state (working directory + scrollback buffer)
_TERMINAL_SESSIONS: Dict[str, Dict[str, Any]] = {}

SHELL_COMMAND_PREFIXES = (
    "$", "!", ">", "dir", "ls", "cd ", "cd..", "pwd", "echo ", "cat ", "type ",
    "git ", "python ", "python3 ", "pip ", "npm ", "npx ", "node ", "cargo ",
    "ipconfig", "ifconfig", "ip ", "ping ", "netstat", "tasklist", "ps ",
    "whoami", "hostname", "mkdir ", "rm ", "del ", "cp ", "copy ", "mv ", "move ",
    "curl ", "wget ", "ssh ", "docker ", "kubectl ", "pytest", "ruff ", "flake8",
    "Get-", "Set-", "Start-", "Stop-", "New-", "Remove-", "Invoke-", "cls", "clear",
)


def is_direct_shell_command(text: str) -> bool:
    """Detect if terminal input is a raw OS shell command vs an AI Agent Prompt."""
    t = text.strip()
    if not t:
        return False
    if t.startswith(("$ ", "! ", "> ")):
        return True
    low = t.lower()
    if low in ("dir", "ls", "pwd", "whoami", "ipconfig", "ifconfig", "hostname", "cls", "clear", "tasklist", "netstat"):
        return True
    for pref in SHELL_COMMAND_PREFIXES:
        if low.startswith(pref.lower()):
            return True
    return False


def get_or_init_terminal_session(node_id: str, initial_cwd: str = "") -> Dict[str, Any]:
    if node_id not in _TERMINAL_SESSIONS:
        s = get_settings()
        cfg_cwd = s.get("default_terminal_cwd", "")
        default_dir = (
            initial_cwd
            if (initial_cwd and os.path.isdir(initial_cwd))
            else (cfg_cwd if (cfg_cwd and os.path.isdir(cfg_cwd)) else str(Path.home()))
        )
        shell_name = "PowerShell + AURA Agent CLI" if IS_WINDOWS else "GNU Bash + AURA Agent CLI"
        _TERMINAL_SESSIONS[node_id] = {
            "node_id": node_id,
            "cwd": default_dir,
            "shell": shell_name,
            "history": [
                {
                    "ts": datetime.now().strftime("%H:%M:%S"),
                    "cmd": "aura-agent --init",
                    "output": (
                        f"[{shell_name}] Diretório ativo: {default_dir}\n"
                        f"• Digite seu PROMPT diretamente neste terminal para o Agente IA trabalhar e mostrar o resultado aqui.\n"
                        f"• Ou digite qualquer comando de terminal (ex: dir, git status, python --version, ou prefixe com $)."
                    ),
                    "exit_code": 0,
                }
            ],
        }
    return _TERMINAL_SESSIONS[node_id]


def append_terminal_log(
    node_id: str,
    header_cmd: str,
    output_body: str,
    exit_code: int = 0,
    elapsed_s: float = 0.0,
) -> Dict[str, Any]:
    """Append an AI Agent working trace + result entry directly into the node's terminal session."""
    sess = get_or_init_terminal_session(node_id)
    entry = {
        "ts": datetime.now().strftime("%H:%M:%S"),
        "cmd": header_cmd,
        "output": output_body[:4500],
        "exit_code": exit_code,
        "elapsed_s": round(elapsed_s, 2),
        "is_agent": True,
    }
    sess["history"].append(entry)
    del sess["history"][:-30]
    return sess


def execute_terminal_command(
    node_id: str,
    command: str,
    notify_mobile: bool = False,
    node_name: str = "Terminal Maestri",
) -> Dict[str, Any]:
    """Execute a real shell command inside a Maestri Canvas Tile's terminal session."""
    sess = get_or_init_terminal_session(node_id)
    cmd_clean = command.strip()
    if cmd_clean.startswith(("$ ", "! ", "> ")):
        cmd_clean = cmd_clean[2:].strip()
    elif cmd_clean.startswith(("$", "!")):
        cmd_clean = cmd_clean[1:].strip()

    if not cmd_clean:
        return {"session": sess, "last_entry": None}

    ts = datetime.now().strftime("%H:%M:%S")
    cwd = sess["cwd"]

    if cmd_clean.lower().startswith("cd "):
        target_dir = cmd_clean[3:].strip().strip('"').strip("'")
        new_path = (Path(cwd) / target_dir).resolve() if not os.path.isabs(target_dir) else Path(target_dir).resolve()
        if new_path.exists() and new_path.is_dir():
            sess["cwd"] = str(new_path)
            entry = {
                "ts": ts,
                "cmd": f"$ {cmd_clean}",
                "output": f"Diretório alterado para: {sess['cwd']}",
                "exit_code": 0,
            }
        else:
            entry = {
                "ts": ts,
                "cmd": f"$ {cmd_clean}",
                "output": f"Erro: Diretório não encontrado: {target_dir}",
                "exit_code": 1,
            }
        sess["history"].append(entry)
        return {"session": sess, "last_entry": entry}

    if cmd_clean.lower() in ("cls", "clear"):
        sess["history"] = []
        return {"session": sess, "last_entry": {"ts": ts, "cmd": cmd_clean, "output": "", "exit_code": 0}}

    s = get_settings()
    timeout_sec = max(5, min(int(s.get("terminal_timeout_sec", 30)), 120))

    start_t = time.time()
    try:
        if IS_WINDOWS:
            creationflags = subprocess.CREATE_NO_WINDOW
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd_clean],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                creationflags=creationflags,
            )
        else:
            proc = subprocess.run(
                ["bash", "-c", cmd_clean],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
        out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        out = out.strip() or "(Comando executado sem saída de texto)"
        code = proc.returncode
    except subprocess.TimeoutExpired:
        out = f"Tempo limite ({timeout_sec}s) atingido para o comando no terminal."
        code = 124
    except Exception as e:
        out = f"Erro ao executar comando: {e}"
        code = 1

    elapsed = round(time.time() - start_t, 2)
    entry = {
        "ts": ts,
        "cmd": f"$ {cmd_clean}",
        "output": out[:3500],
        "exit_code": code,
        "elapsed_s": elapsed,
    }
    sess["history"].append(entry)
    del sess["history"][:-30]

    log_activity("MAESTRI TERM", f"[{node_name}] $ {cmd_clean[:40]} (código {code})")

    if (notify_mobile or elapsed >= 2.0) and s.get("notify_on_terminal", True):
        status_txt = "Concluído com sucesso" if code == 0 else f"Finalizado com código {code}"
        push_mobile_notification(
            title=f"{node_name} — {status_txt}",
            body=f"$ {cmd_clean}\n{out[:180]}",
            category="TERMINAL MAESTRI",
            agent_name=node_name,
        )

    return {"session": sess, "last_entry": entry}

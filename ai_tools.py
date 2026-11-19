import json
import re
from typing import Any, Callable, Dict, List

from file_tools import organize_directory, search_local_files
from github_tools import format_github_context
from storage import (
    add_note,
    add_task,
    complete_task_by_query,
    list_notes,
    list_tasks,
)
from system_tools import (
    check_installed_program,
    clean_temp_files,
    close_application,
    empty_recycle_bin,
    get_network_diagnostics,
    get_system_stats,
    get_top_processes,
    media_and_volume_control,
    open_application,
    run_productivity_routine,
    take_screenshot,
)
from terminal_manager import execute_terminal_command
from web_tools import read_and_summarize_url, search_web


_BLOCKED_SHELL_PATTERNS = (
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "format c:",
    "del /s /q c:\\",
    "rd /s /q c:\\",
    "shutdown",
    "reboot",
    "poweroff",
    "init 0",
    ":(){:|:&};:",
    "dd if=/dev/zero",
)


def is_safe_agent_cmd(cmd: str) -> bool:
    """Block obviously destructive shell commands during autonomous agent tool loops."""
    low = (cmd or "").lower().strip()
    if not low:
        return False
    return not any(b in low for b in _BLOCKED_SHELL_PATTERNS)


def _compact_json(data: Any, max_chars: int = 2400) -> str:
    try:
        raw = json.dumps(data, ensure_ascii=False, default=str)
    except Exception:
        raw = str(data)
    if len(raw) > max_chars:
        return raw[:max_chars] + "... [truncado]"
    return raw


def _tool_get_system_stats(_args: Dict[str, Any]) -> Dict[str, Any]:
    stats = get_system_stats()
    return {
        "ok": True,
        "os": stats.get("os", {}),
        "cpu": stats.get("cpu", {}),
        "ram": stats.get("ram", {}),
        "disk": stats.get("disk", {}),
        "network": stats.get("network", {}),
        "top_processes": (stats.get("top_processes") or [])[:5],
    }


def _tool_get_top_processes(args: Dict[str, Any]) -> Dict[str, Any]:
    limit = max(1, min(int(args.get("limit", 10)), 25))
    sort_by = str(args.get("sort_by", "ram")).lower()
    if sort_by not in ("cpu", "ram"):
        sort_by = "ram"
    procs = get_top_processes(limit=limit, sort_by=sort_by)
    return {"ok": True, "sort_by": sort_by, "processes": procs}


def _tool_open_application(args: Dict[str, Any]) -> Dict[str, Any]:
    target = str(args.get("target") or args.get("app_name") or "").strip()
    if not target:
        return {"ok": False, "error": "Parâmetro 'target' é obrigatório."}
    res = open_application(target)
    return {"ok": bool(res.get("success", True)), **res}


def _tool_close_application(args: Dict[str, Any]) -> Dict[str, Any]:
    target = str(args.get("target") or args.get("name_or_pid") or "").strip()
    if not target:
        return {"ok": False, "error": "Parâmetro 'target' é obrigatório."}
    res = close_application(target)
    return {"ok": bool(res.get("success", False)), **res}


def _tool_take_screenshot(args: Dict[str, Any]) -> Dict[str, Any]:
    open_after = bool(args.get("open_after", False))
    res = take_screenshot(open_after=open_after)
    return {"ok": bool(res.get("success", True)), **res}


def _tool_media_control(args: Dict[str, Any]) -> Dict[str, Any]:
    action = str(args.get("action") or "").strip().lower()
    allowed = {"vol_up", "vol_down", "mute", "play_pause", "next", "prev"}
    if action not in allowed:
        return {"ok": False, "error": f"Ação inválida '{action}'. Use: {', '.join(sorted(allowed))}"}
    res = media_and_volume_control(action)
    return {"ok": bool(res.get("success", True)), **res}


def _tool_clean_temp_files(_args: Dict[str, Any]) -> Dict[str, Any]:
    res = clean_temp_files()
    return {"ok": bool(res.get("success", True)), **res}


def _tool_empty_recycle_bin(_args: Dict[str, Any]) -> Dict[str, Any]:
    res = empty_recycle_bin()
    return {"ok": bool(res.get("success", True)), **res}


def _tool_run_routine(args: Dict[str, Any]) -> Dict[str, Any]:
    routine_id = str(args.get("routine_id") or "").strip().lower()
    if routine_id not in ("modo_dev", "modo_estudo", "modo_faxina"):
        return {"ok": False, "error": "Use 'modo_dev', 'modo_estudo' ou 'modo_faxina'."}
    res = run_productivity_routine(routine_id)
    return {"ok": bool(res.get("success", True)), **res}


def _tool_check_installed_program(args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "Parâmetro 'query' é obrigatório."}
    res = check_installed_program(query)
    return {"ok": True, **res}


def _tool_network_diagnostics(_args: Dict[str, Any]) -> Dict[str, Any]:
    res = get_network_diagnostics()
    return {"ok": True, **res}


def _tool_list_tasks(args: Dict[str, Any]) -> Dict[str, Any]:
    include_done = bool(args.get("include_done", False))
    tasks = list_tasks(include_done=include_done)
    return {"ok": True, "count": len(tasks), "tasks": tasks[:25]}


def _tool_add_task(args: Dict[str, Any]) -> Dict[str, Any]:
    title = str(args.get("title") or "").strip()
    if not title:
        return {"ok": False, "error": "Parâmetro 'title' é obrigatório."}
    priority = str(args.get("priority") or "media").lower()
    if priority not in ("baixa", "media", "alta"):
        priority = "media"
    category = str(args.get("category") or "Geral").strip() or "Geral"
    due_time = str(args.get("due_time") or "").strip()
    task = add_task(title=title, category=category, priority=priority, due_time=due_time)
    return {"ok": True, "task": task}


def _tool_complete_task(args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "Parâmetro 'query' é obrigatório."}
    updated = complete_task_by_query(query)
    if not updated:
        return {"ok": False, "error": f"Nenhuma tarefa pendente encontrada para '{query}'."}
    return {"ok": True, "task": updated}


def _tool_list_notes(_args: Dict[str, Any]) -> Dict[str, Any]:
    notes = list_notes()
    return {"ok": True, "count": len(notes), "notes": notes[:20]}


def _tool_add_note(args: Dict[str, Any]) -> Dict[str, Any]:
    title = str(args.get("title") or "").strip()
    content = str(args.get("content") or "").strip()
    if not title or not content:
        return {"ok": False, "error": "Parâmetros 'title' e 'content' são obrigatórios."}
    note = add_note(title=title, content=content)
    return {"ok": True, "note": note}


def _tool_search_files(args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get("query") or "").strip()
    folder = str(args.get("folder") or "downloads").strip()
    res = search_local_files(query=query, folder=folder, max_results=15)
    return {"ok": bool(res.get("success", True)), **res}


def _tool_organize_folder(args: Dict[str, Any]) -> Dict[str, Any]:
    folder = str(args.get("folder") or "downloads").strip()
    dry_run = bool(args.get("dry_run", True))
    res = organize_directory(folder=folder, dry_run=dry_run)
    return {"ok": bool(res.get("success", True)), **res}


def _tool_search_web(args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "Parâmetro 'query' é obrigatório."}
    max_results = max(1, min(int(args.get("max_results", 4)), 6))
    res = search_web(query, max_results=max_results)
    return {"ok": True, "results": res.get("results", [])}


def _tool_read_url(args: Dict[str, Any]) -> Dict[str, Any]:
    url = str(args.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "Parâmetro 'url' é obrigatório."}
    res = read_and_summarize_url(url)
    return {
        "ok": bool(res.get("content")),
        "url": url,
        "title": res.get("title", ""),
        "content": (res.get("content") or "")[:2000],
    }


def _tool_github_info(args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get("query") or "meus repositórios").strip()
    res = format_github_context(query)
    return {"ok": bool(res.get("ok", True)), "summary": res.get("summary", "")}


def _tool_run_shell(args: Dict[str, Any]) -> Dict[str, Any]:
    command = str(args.get("command") or "").strip()
    if not command:
        return {"ok": False, "error": "Parâmetro 'command' é obrigatório."}
    if not is_safe_agent_cmd(command):
        return {"ok": False, "error": f"Comando bloqueado por política de segurança: {command}"}
    exec_res = execute_terminal_command(
        node_id="chat-agent",
        command=command,
        notify_mobile=False,
        node_name="AURA Agent Shell",
    )
    last = exec_res.get("last_entry") or {}
    return {
        "ok": last.get("exit_code", 0) == 0,
        "cwd": exec_res.get("session", {}).get("cwd", ""),
        "command": command,
        "exit_code": last.get("exit_code", 0),
        "output": (last.get("output") or "")[:2000],
    }


TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "get_system_stats": {
        "description": "Obtém telemetria real do PC: CPU, RAM, Disco, Rede e top processos.",
        "parameters": {},
        "category": "sistema",
        "handler": _tool_get_system_stats,
    },
    "get_top_processes": {
        "description": "Lista os processos que mais consomem CPU ou RAM.",
        "parameters": {"limit": "int (1-25, padrão 10)", "sort_by": "'ram' ou 'cpu'"},
        "category": "sistema",
        "handler": _tool_get_top_processes,
    },
    "open_application": {
        "description": "Abre um aplicativo, pasta ou site no computador.",
        "parameters": {"target": "string (ex: 'chrome', 'vscode', 'calculadora')"},
        "category": "sistema",
        "handler": _tool_open_application,
    },
    "close_application": {
        "description": "Fecha um aplicativo ou processo pelo nome ou PID.",
        "parameters": {"target": "string (ex: 'chrome' ou '1234')"},
        "category": "sistema",
        "handler": _tool_close_application,
    },
    "take_screenshot": {
        "description": "Tira um print (captura de tela) do computador.",
        "parameters": {"open_after": "bool (padrão false)"},
        "category": "sistema",
        "handler": _tool_take_screenshot,
    },
    "media_control": {
        "description": "Controla volume e mídia do sistema.",
        "parameters": {"action": "'vol_up' | 'vol_down' | 'mute' | 'play_pause' | 'next' | 'prev'"},
        "category": "sistema",
        "handler": _tool_media_control,
    },
    "clean_temp_files": {
        "description": "Limpa arquivos temporários e caches do sistema.",
        "parameters": {},
        "category": "otimizacao",
        "handler": _tool_clean_temp_files,
    },
    "empty_recycle_bin": {
        "description": "Esvazia a lixeira do sistema.",
        "parameters": {},
        "category": "otimizacao",
        "handler": _tool_empty_recycle_bin,
    },
    "run_routine": {
        "description": "Executa uma rotina de produtividade ('modo_dev', 'modo_estudo', 'modo_faxina').",
        "parameters": {"routine_id": "'modo_dev' | 'modo_estudo' | 'modo_faxina'"},
        "category": "produtividade",
        "handler": _tool_run_routine,
    },
    "check_installed_program": {
        "description": "Verifica se um programa, jogo ou aplicativo está instalado neste PC.",
        "parameters": {"query": "string (nome do programa)"},
        "category": "sistema",
        "handler": _tool_check_installed_program,
    },
    "network_diagnostics": {
        "description": "Executa diagnóstico de rede (IP local, latência, conectividade).",
        "parameters": {},
        "category": "sistema",
        "handler": _tool_network_diagnostics,
    },
    "list_tasks": {
        "description": "Lista tarefas do usuário.",
        "parameters": {"include_done": "bool (padrão false)"},
        "category": "produtividade",
        "handler": _tool_list_tasks,
    },
    "add_task": {
        "description": "Cria uma nova tarefa.",
        "parameters": {"title": "string", "priority": "'baixa'|'media'|'alta'", "category": "string"},
        "category": "produtividade",
        "handler": _tool_add_task,
    },
    "complete_task": {
        "description": "Marca uma tarefa pendente como concluída pela busca no título.",
        "parameters": {"query": "string"},
        "category": "produtividade",
        "handler": _tool_complete_task,
    },
    "list_notes": {
        "description": "Lista notas salvas do usuário.",
        "parameters": {},
        "category": "produtividade",
        "handler": _tool_list_notes,
    },
    "add_note": {
        "description": "Cria uma nova nota salva.",
        "parameters": {"title": "string", "content": "string"},
        "category": "produtividade",
        "handler": _tool_add_note,
    },
    "search_files": {
        "description": "Busca arquivos locais por nome ou extensão.",
        "parameters": {"query": "string", "folder": "'downloads'|'documentos'|'desktop'|'imagens'"},
        "category": "arquivos",
        "handler": _tool_search_files,
    },
    "organize_folder": {
        "description": "Organiza arquivos soltos de uma pasta em subpastas por categoria.",
        "parameters": {"folder": "string", "dry_run": "bool (padrão true para simulação)"},
        "category": "arquivos",
        "handler": _tool_organize_folder,
    },
    "search_web": {
        "description": "Pesquisa informações atualizadas na internet (DuckDuckGo + Wikipédia).",
        "parameters": {"query": "string", "max_results": "int (1-6)"},
        "category": "web",
        "handler": _tool_search_web,
    },
    "read_url": {
        "description": "Lê e extrai o conteúdo textual de uma URL.",
        "parameters": {"url": "string (http/https)"},
        "category": "web",
        "handler": _tool_read_url,
    },
    "github_info": {
        "description": "Consulta repositórios, commits e status do GitHub via gh CLI e Git local.",
        "parameters": {"query": "string"},
        "category": "dev",
        "handler": _tool_github_info,
    },
    "run_shell": {
        "description": "Executa um comando seguro no shell do sistema (Bash/PowerShell) e retorna a saída.",
        "parameters": {"command": "string"},
        "category": "sistema",
        "handler": _tool_run_shell,
    },
}


def get_tools_catalog() -> List[Dict[str, Any]]:
    """Return serializable tool metadata for API/UI inspection."""
    return [
        {
            "name": name,
            "description": spec["description"],
            "parameters": spec["parameters"],
            "category": spec["category"],
        }
        for name, spec in TOOL_REGISTRY.items()
    ]


def format_tools_for_system_prompt() -> str:
    """Compact tool-calling instructions compatible with every LLM provider in the pool."""
    lines = [
        "FERRAMENTAS DO SISTEMA DISPONÍVEIS (TOOL CALLING):",
        "Quando precisar executar ações reais no computador, consultar hardware/processos, gerenciar tarefas/arquivos, pesquisar na web ou encadear múltiplas ações, emita UM OU MAIS blocos exatamente neste formato:",
        '<tool_call>{"name": "nome_da_ferramenta", "arguments": {"param": "valor"}}</tool_call>',
        "REGRAS DE USO DE FERRAMENTAS:",
        "- Você pode emitir vários blocos <tool_call> na mesma resposta para executar ações em sequência (ex: fechar app + limpar temp + checar RAM).",
        "- Só use <tool_call> quando realmente precisar de dados ou ações reais; para perguntas puramente conceituais ou conversa normal, responda diretamente sem chamar ferramentas.",
        "- Após receber os resultados das ferramentas, responda de forma clara e objetiva em Português do Brasil sem repetir blocos <tool_call> desnecessários.",
        "",
        "Catálogo:",
    ]
    for name, spec in TOOL_REGISTRY.items():
        params = json.dumps(spec["parameters"], ensure_ascii=False) if spec["parameters"] else "{}"
        lines.append(f"- {name}({params}): {spec['description']}")
    return "\n".join(lines)


_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{[\s\S]*?\})\s*</tool_call>", re.IGNORECASE)


def extract_tool_calls(text: str) -> List[Dict[str, Any]]:
    """Extract structured tool calls emitted by an LLM via <tool_call>{...}</tool_call>."""
    if not text or "<tool_call>" not in text.lower():
        return []
    calls: List[Dict[str, Any]] = []
    for match in _TOOL_CALL_RE.finditer(text):
        raw_json = match.group(1).strip()
        try:
            obj = json.loads(raw_json)
            if isinstance(obj, dict) and isinstance(obj.get("name"), str):
                name = obj["name"].strip()
                args = obj.get("arguments") or obj.get("args") or {}
                if not isinstance(args, dict):
                    args = {}
                if name in TOOL_REGISTRY:
                    calls.append({"name": name, "arguments": args})
        except Exception:
            continue
    return calls


def strip_tool_calls(text: str) -> str:
    """Remove <tool_call>...</tool_call> tags from visible assistant text."""
    if not text:
        return ""
    return _TOOL_CALL_RE.sub("", text).strip()


def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a registered AURA tool safely and return a structured result dict."""
    spec = TOOL_REGISTRY.get(name)
    if not spec:
        return {"ok": False, "tool": name, "error": f"Ferramenta desconhecida: '{name}'."}
    handler: Callable[[Dict[str, Any]], Dict[str, Any]] = spec["handler"]
    try:
        result = handler(arguments or {})
        if not isinstance(result, dict):
            result = {"ok": True, "result": result}
        result.setdefault("ok", True)
        return result
    except Exception as exc:
        return {"ok": False, "tool": name, "error": f"Erro ao executar '{name}': {exc}"}


def summarize_tool_result(name: str, result: Dict[str, Any]) -> str:
    """Produce a short human-readable summary for UI badges / SSE tool_result events."""
    if not result.get("ok"):
        return str(result.get("error") or result.get("message") or "Falha na execução")[:140]
    if result.get("message"):
        return str(result["message"])[:140]
    if name == "get_system_stats":
        cpu = result.get("cpu", {}).get("percent", "?")
        ram = result.get("ram", {}).get("percent", "?")
        return f"CPU {cpu}% • RAM {ram}%"
    if name == "get_top_processes":
        procs = result.get("processes") or []
        return f"{len(procs)} processos coletados"
    if name == "list_tasks":
        return f"{result.get('count', 0)} tarefa(s)"
    if name == "search_files":
        return f"{result.get('count', 0)} arquivo(s) encontrado(s)"
    if name == "search_web":
        return f"{len(result.get('results') or [])} resultado(s) web"
    if name == "run_shell":
        return f"exit_code={result.get('exit_code', 0)}"
    return "Concluído"


def format_tool_result_for_llm(name: str, arguments: Dict[str, Any], result: Dict[str, Any]) -> str:
    return (
        f"[RESULTADO DA FERRAMENTA `{name}` args={_compact_json(arguments, 300)}]:\n"
        f"{_compact_json(result, 2200)}"
    )

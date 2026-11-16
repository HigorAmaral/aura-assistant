import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

from storage import (
    list_tasks,
    add_task,
    complete_task_by_query,
    list_notes,
    add_note,
    get_settings,
    log_activity,
    get_chat_history,
    append_chat_history,
)
from system_tools import (
    IS_WINDOWS,
    get_system_stats,
    open_application,
    close_application,
    take_screenshot,
    media_and_volume_control,
    clean_temp_files,
    empty_recycle_bin,
    lock_workstation,
    run_productivity_routine,
    check_installed_program,
)
from file_tools import search_local_files, organize_directory, create_text_file
from web_tools import search_web, read_and_summarize_url
from github_tools import format_github_context, get_local_git_summary
from memory_engine import (
    auto_learn_from_message,
    match_custom_trigger,
    get_memory_context_for_prompt,
    get_memory_stats,
)
from free_ai_router import call_with_free_ai_failover
from remote_bridge import push_mobile_notification
from terminal_manager import (
    execute_terminal_command,
    get_or_init_terminal_session,
    append_terminal_log,
    is_direct_shell_command,
)
import time

BASE_SYSTEM_INSTRUCTION = (
    "Você é a AURA OS 5.0 (Edição Maestri Workspace), uma Arquiteta de Sistemas Sênior e Plataforma "
    "de Orquestração Multi-Agentes com terminais ao vivo em um quadro infinito 2D.\n"
    "PRINCÍPIOS DE ENGENHARIA PROFISSIONAL:\n"
    "1. Evidência acima de suposição: você TEM acesso externo real ao sistema (PowerShell/Bash, arquivos, "
    "processos, CPU/RAM/Disco, pesquisa web em tempo real, leitura de URLs e GitHub via `gh` CLI e Git, "
    "além de Vercel, Supabase e Antigravity). Use os dados reais do contexto ou suas ferramentas; NUNCA invente saídas, caminhos ou métricas.\n"
    "2. Precisão técnica e profundidade: entregue respostas de nível sênior, estruturadas, com comandos exatos, "
    "código limpo pronto para produção, análise de causa raiz e próximos passos acionáveis.\n"
    "3. Objetividade: vá direto ao ponto, sem floreios, em Português do Brasil claro."
)

_CHAT_HISTORY: List[Dict[str, str]] = []


def _infer_task_type(text: str, role: str = "") -> str:
    combined = f"{role} {text}".lower()
    if any(k in combined for k in ("código", "codigo", "python", "javascript", "typescript", "sql", "bug", "erro", "script", "api", "fastapi", "react", "html", "css", "git", "debug", "refator", "coder")):
        return "coding"
    if any(k in combined for k in ("planej", "arquitet", "estratég", "estrateg", "auditor", "revis", "seguran")):
        return "planning"
    if any(k in combined for k in ("pesquis", "web", "notícia", "noticia", "tendência", "tendencia", "buscar", "mercado")):
        return "research"
    if any(k in combined for k in ("resum", "síntese", "sintese", "consolid", "relatório", "relatorio")):
        return "synthesis"
    return "general"



def build_system_instruction(extra_role: str = "") -> str:
    s = get_settings()
    name = s.get("assistant_name", "AURA")
    style = s.get("response_style", "direto_tecnico")
    custom = (s.get("custom_system_prompt") or "").strip()

    style_map = {
        "direto_tecnico": "Seja direto, técnico, objetivo e focado em soluções práticas.",
        "detalhado_didatico": "Explique passo a passo de forma didática, detalhada e com exemplos claros.",
        "executivo_resumido": "Responda em formato de resumo executivo enxuto com bullet points de alto impacto.",
    }
    parts = [
        f"Seu nome é {name}. " + BASE_SYSTEM_INSTRUCTION,
        f"ESTILO DE RESPOSTA: {style_map.get(style, style_map['direto_tecnico'])}",
    ]
    if custom:
        parts.append(f"INSTRUÇÃO PERSONALIZADA DO USUÁRIO: {custom}")
    if extra_role:
        parts.append(f"PAPEL DO AGENTE ATUAL: {extra_role}")
    if s.get("auto_learn_memory", True):
        mem_ctx = get_memory_context_for_prompt()
        if mem_ctx:
            parts.append(mem_ctx)
    return "\n\n".join(parts)


def _extract_installed_check_target(text: str) -> str:
    """Detect questions asking if an app/game/program is installed on this PC and extract its name."""
    t = text.strip().rstrip("?!.")
    patterns = [
        r"(?:eu\s+)?tenho\s+(?:o\s+|a\s+)?(?:jogo\s+|app\s+|aplicativo\s+|programa\s+)?(.+?)\s+instalad[oa](?:\s+(?:no|em|aqui).*)?$",
        r"(?:o\s+|a\s+)?(?:jogo\s+|app\s+|aplicativo\s+|programa\s+)?(.+?)\s+(?:est[aá]|ta)\s+instalad[oa](?:\s+(?:no|em|aqui).*)?$",
        r"(?:verifique|verifica|verificar|veja|confira|cheque|checar)\s+se\s+(?:eu\s+)?(?:tenho|tem|est[aá]\s+instalad[oa])\s+(?:o\s+|a\s+)?(.+?)(?:\s+instalad[oa].*|\s+no\s+(?:meu\s+)?(?:pc|computador|sistema).*)?$",
        r"(?:tem|existe)\s+(?:o\s+|a\s+)?(?:jogo\s+|app\s+|aplicativo\s+|programa\s+)?(.+?)\s+instalad[oa](?:\s+(?:no|em|aqui).*)?$",
    ]
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            candidate = re.sub(r"^(?:o|a|um|uma|algum|alguma)\s+", "", candidate, flags=re.IGNORECASE).strip()
            if 1 < len(candidate) <= 60:
                return candidate
    return ""


def _handle_conversational_intent(text: str) -> Optional[str]:
    """Handle greetings, thanks, farewells, and capability questions without triggering web search."""
    clean = re.sub(r"^(?:aura[,\s!.:;-]*)", "", text.strip(), flags=re.IGNORECASE).strip()
    norm = re.sub(r"[!?.,:;]+$", "", clean).strip().lower()
    if not norm:
        return "Olá! Estou online e pronta para ajudar no seu PC, terminal, GitHub, pesquisas web ou no Quadro Maestri 2D. O que deseja fazer?"

    greetings = {
        "oi", "ola", "olá", "eae", "e ai", "e aí", "opa", "fala", "salve",
        "bom dia", "boa tarde", "boa noite", "hello", "hi", "hey",
        "tudo bem", "tudo bom", "como vai", "como voce esta", "como você está",
        "oi tudo bem", "ola tudo bem", "olá tudo bem",
    }
    if norm in greetings or any(norm.startswith(g + " ") and len(norm) <= 24 for g in ("oi", "olá", "ola", "bom dia", "boa tarde", "boa noite")):
        return (
            "Olá! Tudo ótimo por aqui. Estou conectada ao seu computador e pronta para executar comandos.\n\n"
            "Posso te ajudar com:\n"
            "- **Sistema & Apps:** abrir/fechar programas, ver CPU/RAM/Rede, tirar print ou rodar rotinas\n"
            "- **GitHub & Código:** listar seus repositórios, ver commits, status do Git e arquivos locais\n"
            "- **Terminal & Maestri 2D:** rodar comandos PowerShell/Python e orquestrar agentes\n"
            "- **Web & Tarefas:** pesquisar na internet, resumir links e gerenciar tarefas/lembretes"
        )

    thanks = {"obrigado", "obrigada", "valeu", "vlw", "tmj", "thanks", "thank you", "show", "top", "beleza", "blz", "ok", "certo"}
    if norm in thanks:
        return "Por nada! Se precisar de mais alguma coisa no PC, GitHub ou na web, é só chamar."

    farewells = {"tchau", "ate mais", "até mais", "flw", "falou", "bye", "ate logo", "até logo"}
    if norm in farewells:
        return "Até mais! Continuo rodando em segundo plano caso precise."

    if any(p in norm for p in ("quem e voce", "quem é você", "o que voce faz", "o que você faz", "quais seus acessos", "voce tem acesso", "você tem acesso", "ajuda", "help")):
        return (
            "Sou a **AURA OS 5.0**, sua assistente pessoal integrada ao sistema.\n\n"
            "**Acessos externos e locais ativos:**\n"
            "- **GitHub (`gh` CLI + Git):** acesso autenticado aos seus repositórios, commits e status local\n"
            "- **Computador & Terminal:** execução de comandos PowerShell/Bash, arquivos locais e apps instalados\n"
            "- **Web em Tempo Real:** busca DuckDuckGo/Wikipédia e leitura/resumo de URLs\n"
            "- **Celular 4G/5G:** notificações push e controle remoto"
        )
    return None


def _is_github_intent(lower: str) -> bool:
    return any(
        kw in lower
        for kw in (
            "github",
            "repositório",
            "repositorio",
            "repositórios",
            "repositorios",
            "meus repos",
            "listar repos",
            "git status",
            "últimos commits",
            "ultimos commits",
        )
    )


def run_smart_local_agent(message: str, fallback_only: bool = False) -> Dict[str, Any]:
    text = message.strip()
    lower = text.lower()
    actions_taken: List[Dict[str, Any]] = []

    conv_reply = _handle_conversational_intent(text)
    if conv_reply:
        return {"reply": conv_reply, "actions_taken": actions_taken, "provider": "AURA Conversational Core"}

    mapped_cmd = match_custom_trigger(text)
    if mapped_cmd and mapped_cmd.lower() != lower:
        actions_taken.append({"tool": "custom_trigger", "args": {"phrase": text, "mapped": mapped_cmd}})
        sub_res = run_smart_local_agent(mapped_cmd, fallback_only=False)
        sub_res["actions_taken"] = actions_taken + sub_res.get("actions_taken", [])
        sub_res["reply"] = f"**[Atalho da Memória: '{text}' → '{mapped_cmd}']**\n\n" + sub_res["reply"]
        return sub_res

    learned_items = auto_learn_from_message(text)
    if learned_items:
        for item in learned_items:
            actions_taken.append({"tool": f"memory_{item['type']}", "args": item["data"]})
        if any(
            lower.startswith(prefix)
            for prefix in ("quando eu disser", "quando eu falar", "lembre-se que", "lembre que", "aprenda que", "guarde na memória", "guarde na memoria")
        ):
            first = learned_items[0]
            if first["type"] == "trigger":
                d = first["data"]
                return {
                    "reply": f"**Novo Hábito Aprendido!** Sempre que você disser `\"{d['phrase']}\"`, executarei automaticamente `\"{d['action_command']}\"`.",
                    "actions_taken": actions_taken,
                    "provider": "AURA Memory Engine",
                }
            else:
                d = first["data"]
                return {
                    "reply": f"**Memória Registrada ({d['category']}):** *\"{d['fact']}\"*",
                    "actions_taken": actions_taken,
                    "provider": "AURA Memory Engine",
                }

    if any(kw in lower for kw in ("print", "screenshot", "captura de tela", "capturar tela", "foto da tela")):
        res = take_screenshot(open_after=True)
        actions_taken.append({"tool": "take_screenshot", "args": {"open_after": True}, "result": res})
        return {"reply": res["message"], "actions_taken": actions_taken, "provider": "AURA System Core"}

    if any(kw in lower for kw in ("aumentar volume", "aumente o volume", "subir volume", "volume +")):
        res = media_and_volume_control("vol_up")
        actions_taken.append({"tool": "media_and_volume_control", "args": {"action": "vol_up"}, "result": res})
        return {"reply": res["message"], "actions_taken": actions_taken, "provider": "AURA System Core"}
    if any(kw in lower for kw in ("diminuir volume", "abaixe o volume", "abaixar volume", "volume -")):
        res = media_and_volume_control("vol_down")
        actions_taken.append({"tool": "media_and_volume_control", "args": {"action": "vol_down"}, "result": res})
        return {"reply": res["message"], "actions_taken": actions_taken, "provider": "AURA System Core"}
    if any(kw in lower for kw in ("mutar", "silenciar", "mudo", "tirar som")):
        res = media_and_volume_control("mute")
        actions_taken.append({"tool": "media_and_volume_control", "args": {"action": "mute"}, "result": res})
        return {"reply": res["message"], "actions_taken": actions_taken, "provider": "AURA System Core"}
    if any(kw in lower for kw in ("pausar música", "tocar música", "play", "pause")):
        res = media_and_volume_control("play_pause")
        actions_taken.append({"tool": "media_and_volume_control", "args": {"action": "play_pause"}, "result": res})
        return {"reply": res["message"], "actions_taken": actions_taken, "provider": "AURA System Core"}

    if any(kw in lower for kw in ("limpar temp", "arquivos temporários", "arquivos temporarios", "limpar cache")):
        res = clean_temp_files()
        actions_taken.append({"tool": "clean_temp_files", "args": {}, "result": res})
        return {"reply": res["message"], "actions_taken": actions_taken, "provider": "AURA System Core"}

    if any(kw in lower for kw in ("esvaziar lixeira", "esvazie a lixeira", "limpar lixeira")):
        res = empty_recycle_bin()
        actions_taken.append({"tool": "empty_recycle_bin", "args": {}, "result": res})
        return {"reply": res["message"], "actions_taken": actions_taken, "provider": "AURA System Core"}

    if "modo dev" in lower or "rotina dev" in lower:
        res = run_productivity_routine("modo_dev")
        actions_taken.append({"tool": "run_productivity_routine", "args": {"routine_id": "modo_dev"}, "result": res})
        return {"reply": res["message"], "actions_taken": actions_taken, "provider": "AURA System Core"}
    if "modo estudo" in lower or "rotina estudo" in lower:
        res = run_productivity_routine("modo_estudo")
        actions_taken.append({"tool": "run_productivity_routine", "args": {"routine_id": "modo_estudo"}, "result": res})
        return {"reply": res["message"], "actions_taken": actions_taken, "provider": "AURA System Core"}
    if any(kw in lower for kw in ("modo faxina", "faxina completa")):
        res = run_productivity_routine("modo_faxina")
        actions_taken.append({"tool": "run_productivity_routine", "args": {"routine_id": "modo_faxina"}, "result": res})
        return {"reply": res["message"], "actions_taken": actions_taken, "provider": "AURA System Core"}

    install_target = _extract_installed_check_target(text)
    if install_target:
        res = check_installed_program(install_target)
        actions_taken.append({"tool": "check_installed_program", "args": {"query": install_target}, "result": res})
        return {"reply": res["summary"], "actions_taken": actions_taken, "provider": "AURA System Inspector"}

    # Full-system direct shell execution via chat/voice (e.g. "execute no powershell ...", "comando: ...", "$ ...")
    shell_match = re.match(
        r"^(?:aura[,\s]+)?(?:(?:execute|rode|rodar|executar)\s+(?:no\s+)?(?:terminal|powershell|cmd|bash|shell)[:\s]+|comando[:\s]+|\$\s+)(.+)$",
        text,
        re.IGNORECASE,
    )
    if shell_match:
        raw_cmd = shell_match.group(1).strip()
        exec_res = execute_terminal_command(node_id="chat-system", command=raw_cmd, notify_mobile=False, node_name="Acesso Total SO")
        last_e = exec_res.get("last_entry") or {}
        actions_taken.append({"tool": "execute_terminal_command", "args": {"command": raw_cmd}, "result": last_e})
        return {
            "reply": f"**Executado no Sistema (`{exec_res['session']['cwd']}`):**\n`{raw_cmd}`\n\n```\n{last_e.get('output', '')}\n```",
            "actions_taken": actions_taken,
            "provider": "AURA Full System Shell",
        }

    if any(kw in lower for kw in ("quais discos", "espaço em disco", "espaco em disco", "meus discos", "partições", "particoes")):
        cmd = "Get-PSDrive -PSProvider FileSystem | Select-Object Name, @{N='Usado_GB';E={[math]::Round($_.Used/1GB,2)}}, @{N='Livre_GB';E={[math]::Round($_.Free/1GB,2)}} | Format-Table -AutoSize" if IS_WINDOWS else "df -h"
        exec_res = execute_terminal_command(node_id="chat-system", command=cmd, notify_mobile=False, node_name="Discos")
        last_e = exec_res.get("last_entry") or {}
        actions_taken.append({"tool": "disk_inventory", "args": {}, "result": last_e})
        return {"reply": f"**Discos & Armazenamento do Sistema:**\n```\n{last_e.get('output', '')}\n```", "actions_taken": actions_taken, "provider": "AURA Full System Shell"}

    if any(kw in lower for kw in ("qual meu ip", "meu endereço ip", "meu ip local", "configuração de rede")):
        cmd = "ipconfig | findstr /i \"IPv4 Gateway\"" if IS_WINDOWS else "ip -4 addr show"
        exec_res = execute_terminal_command(node_id="chat-system", command=cmd, notify_mobile=False, node_name="Rede")
        last_e = exec_res.get("last_entry") or {}
        actions_taken.append({"tool": "network_ip", "args": {}, "result": last_e})
        return {"reply": f"**Endereços de Rede do Sistema:**\n```\n{last_e.get('output', '')}\n```", "actions_taken": actions_taken, "provider": "AURA Full System Shell"}

    open_match = re.search(
        r"^(?:aura[,\s]+)?(?:abra|abrir|abre|inicie|iniciar|executar|execute|launch|open)\s+(?:o\s+|a\s+|os\s+|as\s+)?(?:aplicativo\s+|app\s+|programa\s+|site\s+|pasta\s+)?(.+)$",
        lower,
    )
    if open_match:
        app_target = open_match.group(1).strip().rstrip(".!?")
        res = open_application(app_target)
        actions_taken.append({"tool": "open_application", "args": {"app_name": app_target}, "result": res})
        return {"reply": res["message"], "actions_taken": actions_taken, "provider": "AURA System Core"}

    close_match = re.search(
        r"^(?:aura[,\s]+)?(?:feche|fechar|fecha|encerre|encerrar|matar|pare|close)\s+(?:o\s+|a\s+)?(?:aplicativo\s+|app\s+|programa\s+|processo\s+)?(.+)$",
        lower,
    )
    if close_match:
        target = close_match.group(1).strip().rstrip(".!?")
        res = close_application(target)
        actions_taken.append({"tool": "close_application", "args": {"name_or_pid": target}, "result": res})
        return {"reply": res["message"], "actions_taken": actions_taken, "provider": "AURA System Core"}

    if any(
        kw in lower
        for kw in (
            "uso de cpu",
            "uso da cpu",
            "status do pc",
            "status do sistema",
            "como está o pc",
            "como esta o pc",
            "diagnóstico",
            "diagnostico",
        )
    ):
        stats = get_system_stats()
        actions_taken.append({"tool": "get_system_stats", "args": {}, "result": stats})
        top_procs = ", ".join([f"{p['name']} ({p['memory_percent']}%)" for p in stats["top_processes"][:4]])
        reply = (
            f"**Diagnóstico em Tempo Real ({stats['os']['label']}):**\n\n"
            f"• **CPU:** {stats['cpu']['percent']}% ({stats['cpu']['cores']} núcleos @ {stats['cpu']['freq_ghz']} GHz)\n"
            f"• **Memória RAM:** {stats['ram']['percent']}% ({stats['ram']['used_gb']} GB / {stats['ram']['total_gb']} GB — {stats['ram']['available_gb']} GB livres)\n"
            f"• **Disco ({stats['disk']['mount']}):** {stats['disk']['percent']}% ocupado ({stats['disk']['free_gb']} GB livres)\n"
            f"• **Rede:** ↓ {stats['network']['down_kbs']} KB/s | ↑ {stats['network']['up_kbs']} KB/s | IP `{stats['network']['local_ip']}`\n"
            f"• **Top Processos:** {top_procs}"
        )
        return {"reply": reply, "actions_taken": actions_taken, "provider": "AURA System Core"}

    task_match = re.search(
        r"(?:adicione|adicionar|crie|criar|nova|anote a)\s+(?:uma\s+|a\s+)?tarefa[:\s]+(.+)$",
        text,
        re.IGNORECASE,
    )
    if task_match:
        raw_task = task_match.group(1).strip()
        priority = "media"
        if "prioridade alta" in raw_task.lower() or "urgente" in raw_task.lower():
            priority = "alta"
            raw_task = re.sub(r"(?:com\s+)?prioridade\s+alta|urgente", "", raw_task, flags=re.IGNORECASE).strip(" ,.-")
        elif "prioridade baixa" in raw_task.lower():
            priority = "baixa"
            raw_task = re.sub(r"(?:com\s+)?prioridade\s+baixa", "", raw_task, flags=re.IGNORECASE).strip(" ,.-")

        task = add_task(title=raw_task, category="Geral", priority=priority)
        actions_taken.append({"tool": "add_task", "args": {"title": raw_task, "priority": priority}, "result": task})
        return {
            "reply": f"Tarefa **\"{task['title']}\"** adicionada (Prioridade: **{priority.upper()}**)!",
            "actions_taken": actions_taken,
            "provider": "AURA Task Core",
        }

    done_match = re.search(
        r"(?:conclua|concluir|finalizar|finalize|marcar como conclu[ií]da)\s+(?:a\s+)?tarefa\s+(.+)$",
        lower,
    )
    if done_match:
        q = done_match.group(1).strip()
        updated = complete_task_by_query(q)
        actions_taken.append({"tool": "complete_task", "args": {"query": q}, "result": updated})
        if updated:
            return {
                "reply": f"Tarefa **\"{updated['title']}\"** marcada como concluída!",
                "actions_taken": actions_taken,
                "provider": "AURA Task Core",
            }

    if any(kw in lower for kw in ("minhas tarefas", "listar tarefas", "quais são minhas tarefas", "tarefas pendentes")):
        tasks = list_tasks(include_done=False)
        actions_taken.append({"tool": "list_tasks", "args": {"include_done": False}, "result": tasks})
        if not tasks:
            return {"reply": "Você não tem nenhuma tarefa pendente no momento!", "actions_taken": actions_taken, "provider": "AURA Task Core"}
        lines = [f"• **[#{t['id']}]** {t['title']} *(Prioridade: {t['priority']})*" for t in tasks]
        return {
            "reply": f"**Suas tarefas pendentes ({len(tasks)}):**\n\n" + "\n".join(lines),
            "actions_taken": actions_taken,
            "provider": "AURA Task Core",
        }

    if any(kw in lower for kw in ("organize", "organizar", "arrumar pasta", "limpar downloads")):
        dry_run = any(w in lower for w in ("simule", "simular", "teste", "prévia", "previa"))
        folder = "downloads"
        for f_alias in ("downloads", "documentos", "desktop", "area de trabalho", "área de trabalho", "imagens"):
            if f_alias in lower:
                folder = f_alias
                break
        res = organize_directory(folder=folder, dry_run=dry_run)
        actions_taken.append({"tool": "organize_directory", "args": {"folder": folder, "dry_run": dry_run}, "result": res})
        cats = ", ".join([f"**{k}** ({v})" for k, v in res.get("summary_by_category", {}).items()])
        mode_txt = "Simulação concluída (nenhum arquivo movido)" if dry_run else "Organização executada"
        reply = (
            f"**{mode_txt} em `{res.get('folder')}`:**\n"
            f"• Total de arquivos: **{res.get('total_files', 0)}**\n"
            f"• Categorias: {cats or 'Nenhum arquivo solto.'}"
        )
        return {"reply": reply, "actions_taken": actions_taken, "provider": "AURA File Core"}

    file_search_match = re.search(
        r"(?:busque|buscar|procure|procurar|encontre|achar)\s+(?:arquivos?\s+)?(.+?)(?:\s+na\s+pasta\s+|\s+em\s+)(downloads|documentos|desktop|imagens|area de trabalho|área de trabalho)$",
        lower,
    )
    if file_search_match:
        q = file_search_match.group(1).strip()
        folder = file_search_match.group(2).strip()
        res = search_local_files(query=q, folder=folder)
        actions_taken.append({"tool": "search_local_files", "args": {"query": q, "folder": folder}, "result": res})
        files = res.get("files", [])
        if not files:
            return {"reply": f"Nenhum arquivo contendo **'{q}'** encontrado em `{res.get('folder')}`.", "actions_taken": actions_taken, "provider": "AURA File Core"}
        file_lines = [f"• `{f['name']}` ({f['size_kb']} KB) — *{f['modified']}*" for f in files[:10]]
        return {
            "reply": f"**Encontrados {len(files)} arquivo(s) em `{res.get('folder')}`:**\n\n" + "\n".join(file_lines),
            "actions_taken": actions_taken,
            "provider": "AURA File Core",
        }

    return {"reply": "", "actions_taken": actions_taken, "provider": ""}


def _build_smart_web_fallback(
    prompt: str,
    enriched_context_parts: Optional[List[str]] = None,
    failover_chain: Optional[List[str]] = None,
) -> str:
    """
    When all cloud LLMs are in rate-limit cooldown (e.g. Pollinations 45s IP limit) or offline,
    answer factual/general questions using live DuckDuckGo + Wikipedia PT search and any
    collected shell/telemetry context rather than returning a generic placeholder.
    """
    clean_q = re.sub(r"^(?:aura[,\s]+)", "", prompt.strip(), flags=re.IGNORECASE)
    parts: List[str] = []

    # 1. Try local smart agent first (greetings, status do PC, abrir app, tarefas)
    local_res = run_smart_local_agent(clean_q, fallback_only=True)
    if local_res.get("reply"):
        return local_res["reply"]

    # 1b. If user asked about GitHub, return real GitHub CLI data instead of searching the web
    if _is_github_intent(clean_q.lower()):
        gh_ctx = format_github_context(clean_q)
        return gh_ctx.get("summary", "Não foi possível consultar o GitHub agora.")

    # 2. Try live Web + Wikipedia PT search only for genuine informational/search queries
    conv_guard = _handle_conversational_intent(clean_q)
    if conv_guard:
        return conv_guard

    if len(clean_q) >= 3:
        w_res = search_web(clean_q, max_results=4)
        if w_res.get("results"):
            lines = []
            for r in w_res["results"][:3]:
                snip = (r.get("snippet") or "").strip()
                if snip:
                    lines.append(f"• {r['title']}:\n  {snip}\n  Fonte: {r['url']}")
            if lines:
                parts.append(f"🔎 Resposta encontrada via Pesquisa Web & Wikipédia para \"{clean_q}\":\n\n" + "\n\n".join(lines))

    # 3. Include only fresh shell/telemetry context collected for THIS prompt (never stale terminal history)
    if enriched_context_parts:
        fresh_ctx = [
            c for c in enriched_context_parts
            if not c.startswith("ESTADO ATUAL DO TERMINAL DESTE BLOCO")
            and not c.startswith("SAÍDA DOS BLOCOS ANTERIORES")
        ]
        if fresh_ctx:
            parts.append("📋 Dados coletados do sistema/terminal:\n" + "\n\n".join(fresh_ctx[:2]))

    if not parts:
        parts.append(
            f"Não foi possível obter resposta do provedor de IA gratuito agora para: \"{clean_q}\"."
        )

    parts.append(
        "💡 Dica: O provedor gratuito Pollinations limita 1 requisição a cada 45s por IP. "
        "Para respostas instantâneas e ilimitadas, adicione uma chave gratuita do Google Gemini ou Groq na Aba 7 (Configurações do Sistema)."
    )
    return "\n\n".join(parts)


def process_chat_message(message: str, preferred_model: Optional[str] = None) -> Dict[str, Any]:
    local_res = run_smart_local_agent(message, fallback_only=True)
    if local_res.get("reply"):
        return local_res

    actions_taken = local_res.get("actions_taken", [])

    lower = message.lower()
    extra_contexts: List[str] = []

    if _is_github_intent(lower):
        gh_ctx = format_github_context(message)
        actions_taken.append({"tool": "github_cli", "args": {"query": message}, "result": {"ok": gh_ctx.get("ok")}})
        if gh_ctx.get("summary"):
            extra_contexts.append(f"[DADOS REAIS DO GITHUB DO USUÁRIO VIA GH CLI]:\n{gh_ctx['summary']}")

    url_match = re.search(r"https?://[^\s<>\"']+", message)
    if url_match and not any(v in lower for v in ("abra ", "abrir ", "acesse ")):
        target_url = url_match.group(0).rstrip(".,);")
        url_res = read_and_summarize_url(target_url)
        actions_taken.append({"tool": "read_and_summarize_url", "args": {"url": target_url}, "result": {"ok": bool(url_res.get("content"))}})
        if url_res.get("content"):
            extra_contexts.append(f"[CONTEÚDO DA URL '{target_url}']:\n{url_res['content'][:2500]}")

    if any(w in lower for w in ("pesquise", "pesquisar", "notícias", "noticias", "web", "internet", "tendências", "tendencias")):
        q = re.sub(r"^(?:pesquise|pesquisar|busque na web|sobre)\s+", "", message, flags=re.IGNORECASE).strip()
        w_res = search_web(q, max_results=4)
        actions_taken.append({"tool": "search_web", "args": {"query": q}, "result": w_res})
        if w_res.get("results"):
            snippets = "\n".join([f"- {r['title']}: {r['snippet']} ({r['url']})" for r in w_res["results"]])
            extra_contexts.append(f"[RESULTADOS DA WEB EM TEMPO REAL PARA '{q}']:\n{snippets}")

    web_context = ("\n\n" + "\n\n".join(extra_contexts)) if extra_contexts else ""

    if not _CHAT_HISTORY:
        try:
            for row in get_chat_history(6):
                _CHAT_HISTORY.append({"role": row["role"], "content": row["content"]})
        except Exception:
            pass

    history_block = ""
    if _CHAT_HISTORY:
        recent_turns = _CHAT_HISTORY[-6:]
        history_block = (
            "[HISTÓRICO RECENTE DA CONVERSA]:\n"
            + "\n".join(f"{t['role'].upper()}: {t['content'][:400]}" for t in recent_turns)
            + "\n\n"
        )

    sys_prompt = build_system_instruction()
    ai_out = call_with_free_ai_failover(
        user_prompt=history_block + f"MENSAGEM ATUAL DO USUÁRIO:\n{message}" + web_context,
        system_prompt=sys_prompt,
        preferred_model_id=preferred_model,
        task_type=_infer_task_type(message),
    )

    if ai_out["success"]:
        _CHAT_HISTORY.append({"role": "user", "content": message})
        _CHAT_HISTORY.append({"role": "assistant", "content": ai_out["reply"]})
        if len(_CHAT_HISTORY) > 16:
            del _CHAT_HISTORY[:-16]
        try:
            append_chat_history("user", message)
            append_chat_history("assistant", ai_out["reply"], provider=ai_out.get("provider_name", ""))
        except Exception:
            pass

        failover_note = ""
        if ai_out.get("failover_chain"):
            failover_note = f"\n\n*Rotação Automática de IA: {', '.join(ai_out['failover_chain'])} → Atendido por **{ai_out['provider_name']}***"

        # Send notification to smartphone that AI finished responding!
        push_mobile_notification(
            title=f"IA Concluída ({ai_out['provider_name']})",
            body=ai_out["reply"][:240],
            category="IA CONCLUÍDA",
            agent_name=ai_out["provider_name"],
        )

        return {
            "reply": ai_out["reply"] + failover_note,
            "actions_taken": actions_taken,
            "provider": ai_out["provider_name"],
            "model_id": ai_out["model_id"],
            "failover_chain": ai_out.get("failover_chain", []),
        }

    fallback_reply = _build_smart_web_fallback(message, failover_chain=ai_out.get("failover_chain"))
    return {
        "reply": fallback_reply,
        "actions_taken": actions_taken,
        "provider": "AURA Web + Motor Local",
    }


def _is_safe_agent_cmd(cmd: str) -> bool:
    """Block obviously destructive shell commands during autonomous agent tool loops."""
    low = (cmd or "").lower().strip()
    if not low:
        return False
    blocked = (
        "rm -rf /",
        "rm -rf /*",
        "mkfs",
        "format c:",
        "del /s /q c:\\",
        "rd /s /q c:\\",
        "shutdown",
        "reboot",
        ":(){:|:&};:",
    )
    return not any(b in low for b in blocked)


def _infer_shell_cmd_for_prompt(prompt: str) -> str:
    """If the user's prompt asks to inspect files, git, python, or network, infer a safe read-only shell command."""
    p = prompt.lower()
    # Explicit [CMD: ...] tag
    m = re.search(r"\[cmd:\s*([^\]]+)\]", prompt, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    if any(w in p for w in ("arquivos desta pasta", "listar arquivos", "o que tem na pasta", "diretório atual", "estrutura do projeto")):
        return "Get-ChildItem | Select-Object Mode, LastWriteTime, Length, Name" if IS_WINDOWS else "ls -la"
    if "git status" in p or "repositório git" in p:
        return "git status"
    if any(w in p for w in ("git log", "últimos commits", "ultimos commits", "histórico git")):
        return "git log -n 8 --oneline"
    if "git diff" in p or "alterações no git" in p:
        return "git diff --stat"
    if "versão do python" in p or "python instalado" in p:
        return "python --version"
    if "versão do node" in p or "node instalado" in p:
        return "node --version"
    if "docker" in p and any(w in p for w in ("containers", "rodando", "status", "ps")):
        return "docker ps"
    if any(w in p for w in ("portas abertas", "conexões de rede", "netstat")):
        return "netstat -ano | Select-Object -First 15" if IS_WINDOWS else "ss -tuln"
    return ""


def run_maestri_canvas_agent(
    node_id: str,
    agent_name: str,
    agent_role: str,
    model_id: str,
    prompt: str,
    terminal_cmd: str = "",
    upstream_outputs: List[Dict[str, str]] = [],
    on_step: Optional[Callable[[str], None]] = None,
    ipc_ask_depth: int = 0,
) -> Dict[str, Any]:
    """
    Execute a Maestri 2D Workspace Tile where the prompt, agent working steps, shell commands,
    and final AI output all run and display inside the Agent's Live Terminal!
    """
    t0 = time.time()
    s = get_settings()
    enriched_context_parts: List[str] = []
    working_steps: List[str] = []

    def _emit_step(msg: str) -> None:
        working_steps.append(msg)
        if on_step:
            try:
                on_step(msg)
            except Exception:
                pass

    term_session = get_or_init_terminal_session(node_id)
    _emit_step(f"⚙ [INICIANDO AGENTE] {agent_name} ({model_id})")
    working_steps.append(f"├─ Papel: {agent_role}")
    working_steps.append(f"├─ Diretório do Terminal: {term_session['cwd']}")

    # 1. Determine if a shell command should run first
    cmd_to_run = terminal_cmd.strip()
    if not cmd_to_run and s.get("agent_auto_exec_shell", True):
        cmd_to_run = _infer_shell_cmd_for_prompt(prompt)

    if cmd_to_run:
        working_steps.append(f"├─ 💻 [EXECUTANDO NO SHELL] $ {cmd_to_run}")
        exec_res = execute_terminal_command(
            node_id=node_id,
            command=cmd_to_run,
            notify_mobile=False,
            node_name=agent_name,
        )
        term_session = exec_res["session"]
        last_entry = exec_res.get("last_entry")
        if last_entry:
            enriched_context_parts.append(
                f"SAÍDA DO TERMINAL DESTE BLOCO (`{last_entry['cmd']}` em `{term_session['cwd']}`):\n{last_entry['output']}"
            )
    elif term_session.get("history"):
        last_h = term_session["history"][-1]
        enriched_context_parts.append(
            f"ESTADO ATUAL DO TERMINAL DESTE BLOCO (`{term_session['cwd']}`):\nÚltima entrada: `{last_h['cmd']}`\nSaída: {last_h['output'][:700]}"
        )

    # 2. Collect upstream connected tiles
    if upstream_outputs:
        up_names = [u["name"] for u in upstream_outputs if u.get("output")]
        if up_names:
            working_steps.append(f"├─ 🔗 [CONEXÕES 2D] Recebendo contexto de: {', '.join(up_names)}")
        up_lines = [f"--- Bloco Conectado [{u['name']}]:\n{u['output']}" for u in upstream_outputs if u.get("output")]
        if up_lines:
            enriched_context_parts.append("SAÍDA DOS BLOCOS ANTERIORES NO CANVAS:\n" + "\n\n".join(up_lines))

    role_lower = (agent_role + " " + prompt).lower()
    tools_used: List[str] = []

    install_target = _extract_installed_check_target(prompt)
    if install_target:
        tools_used.append(f"Inspetor de Programas ({install_target})")
        working_steps.append(f"├─ 🔍 [VERIFICANDO NO COMPUTADOR] Escaneando apps sincronizados, Registro do Windows, Steam e Program Files por '{install_target}'...")
        check_res = check_installed_program(install_target)
        elapsed = round(time.time() - t0, 2)
        final_output = check_res["summary"]
        provider_label = "AURA System Inspector"
        working_steps.append(f"└─ ✔ [CONCLUÍDO em {elapsed}s via {provider_label}]")
        terminal_formatted_block = (
            "\n".join(working_steps)
            + f"\n\n═══ RESULTADO DO AGENTE ({agent_name.upper()}) ═══\n"
            + final_output
        )
        term_session = append_terminal_log(
            node_id=node_id,
            header_cmd=f"aura-agent❯ {prompt}",
            output_body=terminal_formatted_block,
            exit_code=0,
            elapsed_s=elapsed,
        )
        log_activity("MAESTRI TERMINAL", f"Agente '{agent_name}' verificou instalação de '{install_target}' ({elapsed}s)")
        if s.get("notify_on_maestri", True):
            push_mobile_notification(
                title=f"Maestri: {agent_name} Concluiu!",
                body=f"[{provider_label}] {final_output[:240]}",
                category="MAESTRI PRONTO",
                agent_name=agent_name,
            )
        return {
            "success": True,
            "output": final_output,
            "provider_used": provider_label,
            "model_id_used": "local:inspector",
            "failover_chain": [],
            "tools_used": tools_used,
            "terminal_session": term_session,
            "elapsed_s": elapsed,
        }

    if any(k in role_lower for k in ("sistema", "pc", "cpu", "ram", "memória", "processos", "ubuntu", "windows", "engenheiro", "performance")):
        stats = get_system_stats()
        tools_used.append("Telemetria OS (CPU/RAM/Processos)")
        working_steps.append(f"├─ 📊 [FERRAMENTA] Lendo telemetria real do sistema ({stats['os']['label']})")
        enriched_context_parts.append(
            f"TELEMETRIA REAL DO COMPUTADOR ({stats['os']['label']}):\n"
            f"CPU: {stats['cpu']['percent']}% | RAM: {stats['ram']['percent']}% ({stats['ram']['used_gb']}/{stats['ram']['total_gb']} GB) | "
            f"Disco Livre: {stats['disk']['free_gb']} GB | Top Processos: {', '.join(p['name'] for p in stats['top_processes'][:5])}"
        )

    if any(k in role_lower for k in ("pesquisa", "web", "internet", "tendência", "tendencias", "notícias", "buscar")) and not _handle_conversational_intent(prompt):
        w_res = search_web(prompt[:80], max_results=3)
        tools_used.append("Busca Web Tempo Real")
        working_steps.append(f"├─ 🌐 [FERRAMENTA] Pesquisando na Web em tempo real: '{prompt[:50]}'")
        if w_res.get("results"):
            snips = "\n".join([f"- {r['title']}: {r['snippet']}" for r in w_res["results"]])
            enriched_context_parts.append(f"PESQUISA WEB EM TEMPO REAL:\n{snips}")

    if _is_github_intent(prompt.lower()):
        gh_ctx = format_github_context(prompt)
        tools_used.append("GitHub CLI (gh)")
        working_steps.append("├─ 🐙 [FERRAMENTA] Consultando GitHub autenticado via gh CLI...")
        if gh_ctx.get("summary"):
            enriched_context_parts.append(f"DADOS REAIS DO GITHUB:\n{gh_ctx['summary']}")

    full_user_prompt = f"PROMPT DO USUÁRIO NO TERMINAL DO AGENTE ({agent_name}):\n{prompt}"
    if enriched_context_parts:
        full_user_prompt += "\n\n" + "\n\n".join(enriched_context_parts)

    task_kind = _infer_task_type(prompt, agent_role)
    agent_tool_guide = (
        f"\n[CAPACIDADES DE AGENTE AUTÔNOMO MAESTRI]\n"
        f"- Você opera no terminal do bloco '{agent_name}' em `{term_session['cwd']}` (SO: {'Windows' if IS_WINDOWS else 'Linux'}).\n"
        f"- Você tem até 5 ciclos autônomos de ferramentas antes de entregar sua resposta final. Para usar uma ferramenta, responda APENAS com uma das tags abaixo:\n"
        f"  • `[EXEC: comando_shell]` — Executa comando real no terminal do bloco.\n"
        f"  • `[LIST_DIR: caminho]` — Lista arquivos e subpastas de um diretório.\n"
        f"  • `[READ_FILE: caminho]` — Lê o conteúdo de um arquivo local.\n"
        f"  • `[WRITE_FILE: caminho | conteúdo]` — Cria ou sobrescreve um arquivo de código/texto.\n"
        f"  • `[PATCH_FILE: caminho | trecho_antigo >>> trecho_novo]` — Substitui cirurgicamente um trecho em arquivo existente.\n"
        f"  • `[RUN_TESTS: comando]` — Executa testes/linters (ex: pytest, ruff check, python3 -m py_compile).\n"
        f"  • `[SEARCH_FILES: padrão]` — Busca arquivos no sistema por nome/extensão.\n"
        f"  • `[WEB_SEARCH: consulta]` — Pesquisa em tempo real na internet.\n"
        f"  • `[READ_URL: https://...]` — Lê e extrai conteúdo de uma página web.\n"
        f"  • `[ASK_AGENT: nome_do_agente | pergunta]` — Consulta outro agente do quadro Maestri 2D (IPC).\n"
        f"- Quando tiver todas as evidências reais necessárias, entregue uma resposta final de nível sênior, estruturada, com achados concretos (arquivos, linhas, comandos, métricas) e próximos passos em Português do Brasil."
    )
    sys_instruction = build_system_instruction(extra_role=f"{agent_name} — {agent_role}{agent_tool_guide}")

    _emit_step("├─ 🧠 [IA PROCESSANDO] Analisando tarefa e planejando ferramentas...")
    ai_res = call_with_free_ai_failover(
        user_prompt=full_user_prompt,
        system_prompt=sys_instruction,
        preferred_model_id=model_id,
        task_type=task_kind,
    )

    # Autonomous ReAct tool loop (up to 5 iterations)
    for _step in range(5):
        if not (ai_res.get("success") and ai_res.get("reply")):
            break
        reply_text = ai_res["reply"].strip()
        exec_match = re.search(r"\[EXEC:\s*([^\]]+)\]", reply_text, re.IGNORECASE)
        list_match = re.search(r"\[LIST_DIR:\s*([^\]]+)\]", reply_text, re.IGNORECASE)
        read_match = re.search(r"\[READ_FILE:\s*([^\]]+)\]", reply_text, re.IGNORECASE)
        patch_match = re.search(r"\[PATCH_FILE:\s*([^|\]]+)\|\s*([\s\S]+?)\s*>>>\s*([\s\S]+)\]", reply_text, re.IGNORECASE)
        write_match = re.search(r"\[WRITE_FILE:\s*([^|\]]+)\|\s*([\s\S]+)\]", reply_text, re.IGNORECASE)
        tests_match = re.search(r"\[RUN_TESTS:\s*([^\]]+)\]", reply_text, re.IGNORECASE)
        search_match = re.search(r"\[SEARCH_FILES:\s*([^\]]+)\]", reply_text, re.IGNORECASE)
        web_match = re.search(r"\[WEB_SEARCH:\s*([^\]]+)\]", reply_text, re.IGNORECASE)
        url_match = re.search(r"\[READ_URL:\s*([^\]]+)\]", reply_text, re.IGNORECASE)
        ask_match = re.search(r"\[ASK_AGENT:\s*([^|\]]+)\|\s*([^\]]+)\]", reply_text, re.IGNORECASE)

        tool_observation = ""
        tool_label = ""

        if exec_match:
            req_cmd = exec_match.group(1).strip()
            if _is_safe_agent_cmd(req_cmd):
                tool_label = f"Shell: {req_cmd}"
                _emit_step(f"├─ 💻 [AGENTE EXECUTOU] $ {req_cmd}")
                exec_res = execute_terminal_command(
                    node_id=node_id,
                    command=req_cmd,
                    notify_mobile=False,
                    node_name=agent_name,
                )
                last_entry = exec_res.get("last_entry") or {}
                tool_observation = f"RESULTADO DE `[EXEC: {req_cmd}]`:\n{(last_entry.get('output') or '(sem saída)')[:2600]}"
        elif list_match:
            req_dir = list_match.group(1).strip().strip('"').strip("'") or "."
            d_obj = Path(req_dir)
            if not d_obj.is_absolute():
                d_obj = Path(term_session["cwd"]) / d_obj
            tool_label = f"Listar: {d_obj.name or req_dir}"
            _emit_step(f"├─ 📂 [LISTANDO DIRETÓRIO] {d_obj}")
            if d_obj.exists() and d_obj.is_dir():
                entries = sorted(d_obj.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:80]
                listing = "\n".join([f"{'[DIR] ' if e.is_dir() else '[FILE]'} {e.name}" for e in entries])
                tool_observation = f"CONTEÚDO DE `{d_obj}`:\n{listing or '(vazio)'}"
            else:
                tool_observation = f"DIRETÓRIO NÃO ENCONTRADO: `{d_obj}`"
        elif patch_match:
            req_path = patch_match.group(1).strip().strip('"').strip("'")
            old_snip = patch_match.group(2)
            new_snip = patch_match.group(3)
            p_obj = Path(req_path)
            if not p_obj.is_absolute():
                p_obj = Path(term_session["cwd"]) / p_obj
            tool_label = f"Patch: {p_obj.name}"
            _emit_step(f"├─ 🔧 [PATCH EM ARQUIVO] {p_obj}")
            if p_obj.exists() and p_obj.is_file():
                try:
                    cur = p_obj.read_text(encoding="utf-8", errors="replace")
                    if old_snip in cur:
                        p_obj.write_text(cur.replace(old_snip, new_snip, 1), encoding="utf-8")
                        tool_observation = f"PATCH APLICADO COM SUCESSO EM `{p_obj}`."
                    else:
                        tool_observation = f"TRECHO ANTIGO NÃO ENCONTRADO EM `{p_obj}`. Leia o arquivo com [READ_FILE] antes de aplicar patch."
                except Exception as p_err:
                    tool_observation = f"ERRO AO APLICAR PATCH EM `{p_obj}`: {p_err}"
            else:
                tool_observation = f"ARQUIVO NÃO ENCONTRADO PARA PATCH: `{p_obj}`"
        elif tests_match:
            test_cmd = tests_match.group(1).strip()
            if _is_safe_agent_cmd(test_cmd):
                tool_label = f"Testes: {test_cmd[:30]}"
                _emit_step(f"├─ 🧪 [RODANDO TESTES] $ {test_cmd}")
                exec_res = execute_terminal_command(
                    node_id=node_id,
                    command=test_cmd,
                    notify_mobile=False,
                    node_name=agent_name,
                )
                last_entry = exec_res.get("last_entry") or {}
                tool_observation = f"RESULTADO DOS TESTES `[RUN_TESTS: {test_cmd}]`:\n{(last_entry.get('output') or '(sem saída)')[:2600]}"
        elif read_match:
            req_path = read_match.group(1).strip().strip('"').strip("'")
            p_obj = Path(req_path)
            if not p_obj.is_absolute():
                p_obj = Path(term_session["cwd"]) / p_obj
            if p_obj.exists() and p_obj.is_file():
                tool_label = f"Leitura: {p_obj.name}"
                _emit_step(f"├─ 📄 [AGENTE LEU ARQUIVO] {p_obj}")
                try:
                    file_txt = p_obj.read_text(encoding="utf-8", errors="replace")[:4500]
                except Exception as f_err:
                    file_txt = f"Erro ao ler arquivo: {f_err}"
                tool_observation = f"CONTEÚDO DE `{p_obj}`:\n{file_txt}"
            else:
                tool_observation = f"ARQUIVO NÃO ENCONTRADO: `{p_obj}`"
        elif write_match:
            req_path = write_match.group(1).strip().strip('"').strip("'")
            req_content = write_match.group(2).strip()
            p_obj = Path(req_path)
            if not p_obj.is_absolute():
                p_obj = Path(term_session["cwd"]) / p_obj
            tool_label = f"Escrita: {p_obj.name}"
            _emit_step(f"├─ ✍️ [AGENTE ESCREVEU ARQUIVO] {p_obj}")
            try:
                p_obj.parent.mkdir(parents=True, exist_ok=True)
                p_obj.write_text(req_content, encoding="utf-8")
                tool_observation = f"ARQUIVO GRAVADO COM SUCESSO: `{p_obj}` ({len(req_content)} bytes)"
            except Exception as w_err:
                tool_observation = f"ERRO AO GRAVAR `{p_obj}`: {w_err}"
        elif search_match:
            pat = search_match.group(1).strip()
            tool_label = f"Busca Arquivos: {pat}"
            _emit_step(f"├─ 🔍 [BUSCANDO ARQUIVOS] {pat}")
            try:
                sf_res = search_local_files(pat, base_dir=term_session["cwd"])
                tool_observation = f"RESULTADO DE `[SEARCH_FILES: {pat}]`:\n{sf_res.get('summary') or sf_res}"
            except Exception as sf_err:
                tool_observation = f"Erro ao buscar arquivos: {sf_err}"
        elif web_match:
            wq = web_match.group(1).strip()
            tool_label = f"Web Search: {wq[:30]}"
            _emit_step(f"├─ 🌐 [PESQUISA WEB] {wq[:50]}")
            w_res = search_web(wq, max_results=4)
            if w_res.get("results"):
                snips = "\n".join([f"- {r['title']}: {r['snippet']} ({r['url']})" for r in w_res["results"]])
                tool_observation = f"RESULTADOS WEB PARA `{wq}`:\n{snips}"
            else:
                tool_observation = f"Nenhum resultado web encontrado para `{wq}`."
        elif url_match:
            u = url_match.group(1).strip()
            tool_label = f"URL: {u[:30]}"
            _emit_step(f"├─ 🔗 [LENDO URL] {u[:60]}")
            u_res = read_and_summarize_url(u)
            tool_observation = f"CONTEÚDO DE `{u}`:\n{(u_res.get('content') or 'Não foi possível extrair texto.')[:3000]}"
        elif ask_match and ipc_ask_depth < 1:
            target_ag = ask_match.group(1).strip()
            sub_q = ask_match.group(2).strip()
            tool_label = f"IPC Ask: {target_ag}"
            _emit_step(f"├─ 🤝 [IPC MAESTRI] Consultando agente '{target_ag}'...")
            try:
                from storage import get_canvas_state
                c_state = get_canvas_state()
                target_node = next(
                    (n for n in c_state.get("nodes", []) if target_ag.lower() in (n.get("name") or "").lower() or target_ag.lower() == (n.get("id") or "").lower()),
                    None,
                )
                if target_node and target_node["id"] != node_id:
                    sub_res = run_maestri_canvas_agent(
                        node_id=target_node["id"],
                        agent_name=target_node.get("name", target_node["id"]),
                        agent_role=target_node.get("role", ""),
                        model_id=target_node.get("model", "free:openai"),
                        prompt=sub_q,
                        ipc_ask_depth=ipc_ask_depth + 1,
                    )
                    tool_observation = f"RESPOSTA DO AGENTE [{target_node.get('name')}]:\n{sub_res.get('output', '')[:2500]}"
                else:
                    tool_observation = f"Agente '{target_ag}' não encontrado no canvas para IPC."
            except Exception as ipc_err:
                tool_observation = f"Erro no IPC com '{target_ag}': {ipc_err}"

        if not tool_observation:
            break

        if tool_label:
            tools_used.append(tool_label)
        full_user_prompt += f"\n\n{tool_observation}\n\nAnalise os dados acima. Se precisar de mais informações, chame outra ferramenta; caso contrário, entregue sua resposta final completa:"
        ai_res = call_with_free_ai_failover(
            user_prompt=full_user_prompt,
            system_prompt=sys_instruction,
            preferred_model_id=model_id,
            task_type=task_kind,
        )

    elapsed = round(time.time() - t0, 2)
    if ai_res.get("success") and ai_res.get("reply"):
        final_output = ai_res["reply"]
        provider_label = ai_res["provider_name"]
    else:
        working_steps.append("├─ 🌐 [FALLBACK INTELIGENTE] IA gratuita em cooldown de cota; consultando Web/Motor Local...")
        final_output = _build_smart_web_fallback(prompt, enriched_context_parts, ai_res.get("failover_chain"))
        provider_label = "AURA Web + Motor Local"
        elapsed = round(time.time() - t0, 2)
    working_steps.append(f"└─ ✔ [CONCLUÍDO em {elapsed}s via {provider_label}]")

    # 3. Write the full working trace + result directly into the Agent's Terminal Session!
    terminal_formatted_block = (
        "\n".join(working_steps)
        + f"\n\n═══ RESULTADO DO AGENTE ({agent_name.upper()}) ═══\n"
        + final_output
    )
    term_session = append_terminal_log(
        node_id=node_id,
        header_cmd=f"aura-agent❯ {prompt}",
        output_body=terminal_formatted_block,
        exit_code=0,
        elapsed_s=elapsed,
    )

    log_activity("MAESTRI TERMINAL", f"Agente '{agent_name}' executou prompt no terminal ({elapsed}s)")

    # 4. Push instant completion notification to the smartphone app (if enabled in settings)!
    if s.get("notify_on_maestri", True):
        push_mobile_notification(
            title=f"Maestri: {agent_name} Concluiu!",
            body=f"[{ai_res['provider_name']}] {final_output[:240]}",
            category="MAESTRI PRONTO",
            agent_name=agent_name,
        )

    return {
        "success": ai_res["success"],
        "output": final_output,
        "provider_used": ai_res["provider_name"],
        "model_id_used": ai_res["model_id"],
        "failover_chain": ai_res.get("failover_chain", []),
        "tools_used": tools_used,
        "terminal_session": term_session,
        "elapsed_s": elapsed,
    }


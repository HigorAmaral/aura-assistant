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
    get_open_ports,
)
from packs_manager import (
    is_pack_enabled,
    get_weather,
    get_finance_quotes,
    get_tech_news,
    translate_text,
    run_dev_util,
    get_daily_briefing,
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
    "Você é a AURA OS, uma Assistente Pessoal de Computador com Inteligência Artificial e Engenharia de Sistemas.\n"
    "PRINCÍPIOS DE OPERAÇÃO:\n"
    "1. Evidência acima de suposição: você TEM acesso externo real ao sistema (PowerShell/Bash, arquivos, "
    "processos, CPU/RAM/Disco, pesquisa web em tempo real, leitura de URLs e GitHub via `gh` CLI e Git). "
    "Use os dados reais do contexto ou suas ferramentas; NUNCA invente saídas, caminhos ou métricas.\n"
    "2. Precisão técnica e profundidade: entregue respostas claras, estruturadas, com comandos exatos, "
    "diagnóstico de causa raiz e próximos passos acionáveis.\n"
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
        return "Olá! Estou online e pronta para ajudar no seu PC, terminal, GitHub ou pesquisas web. O que deseja fazer?"

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
            "- **Terminal & Otimização:** rodar comandos no sistema, limpar temporários e gerenciar processos\n"
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

    if any(kw in lower for kw in ("portas abertas", "portas em uso", "portas escutando", "quais portas")):
        ports = get_open_ports(limit=25)
        actions_taken.append({"tool": "get_open_ports", "args": {}, "result": {"count": len(ports)}})
        if not ports:
            return {"reply": "Nenhuma porta de escuta encontrada ou permissão insuficiente.", "actions_taken": actions_taken, "provider": "AURA Network Inspector"}
        lines = [f"• **{p['protocol']} `:{p['port']}`** ({p['ip']}) — `{p['process']}` (PID {p['pid']})" for p in ports[:15]]
        return {"reply": f"**Portas em Escuta no Sistema ({len(ports)}):**\n\n" + "\n".join(lines), "actions_taken": actions_taken, "provider": "AURA Network Inspector"}

    # --- Packs & External APIs ---
    if is_pack_enabled("productivity") and any(kw in lower for kw in ("briefing diário", "briefing diario", "resumo do meu dia", "resumo do dia")):
        brief = get_daily_briefing()
        actions_taken.append({"tool": "pack_daily_briefing", "args": {}, "result": {"ok": brief.get("ok")}})
        lines = [
            f"**Briefing Diário AURA OS:**",
            f"• **PC:** CPU {brief['system']['cpu_percent']}% | RAM {brief['system']['ram_percent']}% | Disco livre: {brief['system']['disk_free_gb']} GB | Uptime: {brief['system']['uptime']}",
            f"• **Tarefas Pendentes:** {brief['pending_tasks_count']} | **Notas Recentes:** {brief['recent_notes_count']}",
        ]
        if brief.get("top_tasks"):
            lines.append("• **Próximas Tarefas:** " + "; ".join(f"[{t['priority'].upper()}] {t['title']}" for t in brief["top_tasks"][:3]))
        if brief.get("weather"):
            w = brief["weather"]
            lines.append(f"• **Clima ({w['location']}):** {w['temperature_c']}°C — {w['condition']}")
        if brief.get("finance"):
            q_str = " | ".join(f"{q['pair']}: {q['bid']:.2f} ({q['pct_change']:+.2f}%)" for q in brief["finance"][:3])
            lines.append(f"• **Mercado:** {q_str}")
        return {"reply": "\n".join(lines), "actions_taken": actions_taken, "provider": "AURA Pack: Produtividade"}

    weather_match = re.search(
        r"(?:clima|previs[aã]o\s+do\s+tempo|temperatura|como\s+est[aá]\s+o\s+tempo)(?:\s+(?:em|no|na|de|para)\s+([a-zA-ZÀ-ÿ0-9\s-]{2,40}))?",
        text,
        re.IGNORECASE,
    )
    if weather_match and is_pack_enabled("weather") and any(k in lower for k in ("clima", "previsão do tempo", "previsao do tempo", "como está o tempo", "como esta o tempo")):
        city = (weather_match.group(1) or "São Paulo").strip(" ?!.")
        w = get_weather(city)
        actions_taken.append({"tool": "pack_weather", "args": {"city": city}, "result": {"ok": w.get("ok")}})
        if not w.get("ok"):
            return {"reply": w.get("error", "Erro ao consultar clima."), "actions_taken": actions_taken, "provider": "AURA Pack: Clima"}
        fc_lines = [f"  - `{d['date']}`: {d['temp_min']}°C ~ {d['temp_max']}°C ({d['condition']}, chuva {d['rain_prob']}%)" for d in w.get("forecast", [])]
        reply = (
            f"**Clima em {w['location']}:**\n"
            f"• **Agora:** {w['temperature_c']}°C (Sensação {w['feels_like_c']}°C) — **{w['condition']}**\n"
            f"• **Umidade:** {w['humidity_percent']}% | **Vento:** {w['wind_kmh']} km/h\n"
            + ("\n**Próximos dias:**\n" + "\n".join(fc_lines) if fc_lines else "")
        )
        return {"reply": reply, "actions_taken": actions_taken, "provider": "AURA Pack: Clima"}

    if is_pack_enabled("finance") and any(kw in lower for kw in ("dólar", "dolar", "cotação", "cotacao", "cotações", "cotacoes", "bitcoin", "btc", "preço do euro", "preco do euro")):
        fq = get_finance_quotes()
        actions_taken.append({"tool": "pack_finance", "args": {}, "result": {"ok": fq.get("ok")}})
        if not fq.get("ok"):
            return {"reply": fq.get("error", "Erro ao consultar cotações."), "actions_taken": actions_taken, "provider": "AURA Pack: Finanças"}
        lines = [f"• **{q['pair']}** ({q['name']}): **R$ {q['bid']:,.2f}** ({q['pct_change']:+.2f}%)" for q in fq["quotes"]]
        return {"reply": "**Cotações em Tempo Real (AwesomeAPI):**\n\n" + "\n".join(lines), "actions_taken": actions_taken, "provider": "AURA Pack: Finanças"}

    if is_pack_enabled("news") and any(kw in lower for kw in ("notícias de tecnologia", "noticias de tecnologia", "notícias tech", "noticias tech", "hacker news", "tabnews")):
        topic = "hn" if "hacker news" in lower else "pt"
        nw = get_tech_news(topic=topic, limit=6)
        actions_taken.append({"tool": "pack_news", "args": {"topic": topic}, "result": {"ok": nw.get("ok")}})
        if not nw.get("ok"):
            return {"reply": nw.get("error", "Erro ao buscar notícias."), "actions_taken": actions_taken, "provider": "AURA Pack: Notícias"}
        lines = [f"• **{it['title']}** *(+{it['score']})*\n  {it['url']}" for it in nw["items"]]
        return {"reply": f"**Principais Notícias Tech ({nw['items'][0]['source'] if nw['items'] else topic}):**\n\n" + "\n".join(lines), "actions_taken": actions_taken, "provider": "AURA Pack: Notícias"}

    trans_match = re.match(
        r"^(?:aura[,\s]+)?(?:traduza|traduzir)\s+(?:para\s+(?:o\s+)?)?(ingl[eê]s|espanhol|franc[eê]s|alem[aã]o|italiano|japon[eê]s|portugu[eê]s|en|es|fr|de|it|ja|pt)[:\s]+(.+)$",
        text,
        re.IGNORECASE,
    )
    if trans_match and is_pack_enabled("translate"):
        tgt_lang = trans_match.group(1).strip()
        phrase = trans_match.group(2).strip()
        tr = translate_text(phrase, target_lang=tgt_lang)
        actions_taken.append({"tool": "pack_translate", "args": {"target_lang": tgt_lang}, "result": {"ok": tr.get("ok")}})
        if tr.get("ok"):
            return {"reply": f"**Tradução ({tr['source_lang']} → {tr['target_lang']}):**\n\n{tr['translated']}", "actions_taken": actions_taken, "provider": "AURA Pack: Tradutor"}
        return {"reply": tr.get("error", "Erro na tradução."), "actions_taken": actions_taken, "provider": "AURA Pack: Tradutor"}

    if is_pack_enabled("dev_utils"):
        if any(kw in lower for kw in ("gere uma senha", "gerar senha", "criar senha forte", "nova senha")):
            res = run_dev_util("password", {"length": 18})
            actions_taken.append({"tool": "pack_dev_utils", "args": {"action": "password"}, "result": {"ok": True}})
            return {"reply": f"**Senha Forte Gerada ({res['length']} caracteres):**\n`{res['result']}`", "actions_taken": actions_taken, "provider": "AURA Pack: Dev Utils"}
        if any(kw in lower for kw in ("gere um uuid", "gerar uuid", "novo uuid")):
            res = run_dev_util("uuid")
            actions_taken.append({"tool": "pack_dev_utils", "args": {"action": "uuid"}, "result": {"ok": True}})
            return {"reply": f"**UUID v4 Gerado:**\n`{res['result']}`", "actions_taken": actions_taken, "provider": "AURA Pack: Dev Utils"}
        if any(kw in lower for kw in ("meu ip público", "meu ip publico", "ip externo", "qual meu ip externo")):
            res = run_dev_util("public_ip")
            actions_taken.append({"tool": "pack_dev_utils", "args": {"action": "public_ip"}, "result": {"ok": res.get("ok")}})
            if res.get("ok"):
                return {
                    "reply": f"**IP Público:** `{res['ip']}`\n• **Local:** {res['city']}, {res['region']} — {res['country']}\n• **Provedor:** {res['isp']}",
                    "actions_taken": actions_taken,
                    "provider": "AURA Pack: Dev Utils",
                }
        calc_match = re.match(r"^(?:aura[,\s]+)?(?:calcule|calcular|quanto\s+[eé])\s+([0-9\s\+\-\*\/\.\,\(\)\^%×÷]+)[?!.]*$", text, re.IGNORECASE)
        if calc_match:
            expr = calc_match.group(1).strip()
            res = run_dev_util("calc", {"expression": expr})
            if res.get("ok"):
                actions_taken.append({"tool": "pack_dev_utils", "args": {"action": "calc", "expression": expr}, "result": res})
                return {"reply": f"**Resultado:** `{expr}` = **{res['result']}**", "actions_taken": actions_taken, "provider": "AURA Pack: Dev Utils"}

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



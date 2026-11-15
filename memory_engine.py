import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from storage import get_conn, log_activity


def list_memories(limit: int = 50) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, category, fact, confidence, source, created_at FROM memories ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_memory(category: str, fact: str, source: str = "manual", confidence: float = 1.0) -> Dict[str, Any]:
    fact_clean = fact.strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_conn() as conn:
        # Avoid duplicate facts
        existing = conn.execute(
            "SELECT id FROM memories WHERE LOWER(fact) = LOWER(?)", (fact_clean,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE memories SET created_at = ?, confidence = MIN(1.0, confidence + 0.1) WHERE id = ?",
                (now, existing["id"]),
            )
            row = conn.execute("SELECT * FROM memories WHERE id = ?", (existing["id"],)).fetchone()
            return dict(row)

        cur = conn.execute(
            "INSERT INTO memories (category, fact, confidence, source, created_at) VALUES (?, ?, ?, ?, ?)",
            (category.strip() or "Fato", fact_clean, confidence, source, now),
        )
        mid = cur.lastrowid
        row = conn.execute("SELECT * FROM memories WHERE id = ?", (mid,)).fetchone()
    log_activity("MEMÓRIA", f"Novo aprendizado ({category}): {fact_clean[:50]}")
    return dict(row)


def delete_memory(memory_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return cur.rowcount > 0


def list_custom_triggers() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, phrase, action_command, times_used, created_at FROM custom_triggers ORDER BY times_used DESC, id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def add_custom_trigger(phrase: str, action_command: str) -> Dict[str, Any]:
    p_clean = phrase.strip().lower()
    a_clean = action_command.strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO custom_triggers (phrase, action_command, times_used, created_at)
            VALUES (?, ?, 0, ?)
            ON CONFLICT(phrase) DO UPDATE SET action_command = excluded.action_command
            """,
            (p_clean, a_clean, now),
        )
        row = conn.execute("SELECT * FROM custom_triggers WHERE phrase = ?", (p_clean,)).fetchone()
    log_activity("APRENDIZADO", f"Regra criada: '{p_clean}' -> '{a_clean}'")
    return dict(row)


def delete_custom_trigger(trigger_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM custom_triggers WHERE id = ?", (trigger_id,))
        return cur.rowcount > 0


def match_custom_trigger(user_message: str) -> Optional[str]:
    """Check if user_message matches a learned custom trigger/rule and increment usage."""
    lower = user_message.strip().lower().rstrip(".!?")
    with get_conn() as conn:
        rows = conn.execute("SELECT id, phrase, action_command FROM custom_triggers").fetchall()
        for r in rows:
            if lower == r["phrase"] or r["phrase"] in lower:
                conn.execute(
                    "UPDATE custom_triggers SET times_used = times_used + 1 WHERE id = ?",
                    (r["id"],),
                )
                return r["action_command"]
    return None


def auto_learn_from_message(user_message: str) -> List[Dict[str, Any]]:
    """Extract facts, user preferences, or custom rules from natural Portuguese conversation."""
    text = user_message.strip()
    learned: List[Dict[str, Any]] = []

    # 1. Explicit teaching of custom trigger: "quando eu disser X faça Y"
    rule_match = re.search(
        r"quando eu (?:disser|falar|digitar)\s+['\"]?(.+?)['\"]?\s*(?:,|então)?\s*(?:faça|execute|rode|abra)\s+['\"]?(.+?)['\"]?$",
        text,
        re.IGNORECASE,
    )
    if rule_match:
        phrase = rule_match.group(1).strip()
        cmd = rule_match.group(2).strip()
        trig = add_custom_trigger(phrase, cmd)
        learned.append({"type": "trigger", "data": trig})
        return learned

    # 2. Explicit memory command: "lembre-se que ...", "aprenda que ...", "guarde na memória que ..."
    explicit_match = re.search(
        r"^(?:aura[,\s]+)?(?:lembre-se que|lembre que|aprenda que|memorize que|guarde na mem[oó]ria[:\s]+)(.+)$",
        text,
        re.IGNORECASE,
    )
    if explicit_match:
        fact = explicit_match.group(1).strip()
        mem = add_memory("Memória Explícita", fact, source="conversa", confidence=1.0)
        learned.append({"type": "memory", "data": mem})
        return learned

    # 3. Implicit personal facts: "meu nome é ...", "eu trabalho com ...", "eu gosto de ...", "minha linguagem favorita é ..."
    patterns = [
        (r"\bmeu nome [eé]\s+([A-Za-zÀ-ÿ\s]{2,35})", "Identidade", lambda m: f"O nome do usuário é {m.group(1).strip()}"),
        (r"\beu trabalho (?:com|como|na|no)\s+(.{3,60})", "Profissão", lambda m: f"O usuário trabalha com/como {m.group(1).strip()}"),
        (r"\beu estudo\s+(.{3,60})", "Estudos", lambda m: f"O usuário estuda {m.group(1).strip()}"),
        (r"\beu prefiro\s+(.{4,70})", "Preferência", lambda m: f"O usuário prefere {m.group(1).strip()}"),
        (r"\bmeu projeto atual [eé]\s+(.{3,70})", "Projeto", lambda m: f"Projeto atual do usuário: {m.group(1).strip()}"),
    ]
    for pat, cat, builder in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            fact_str = builder(m).rstrip(".,!?")
            mem = add_memory(cat, fact_str, source="auto-aprendizado", confidence=0.92)
            learned.append({"type": "memory", "data": mem})

    return learned


def get_memory_stats() -> Dict[str, Any]:
    """Calculate AURA's Intelligence Level, XP, top habits, and active memories."""
    with get_conn() as conn:
        mem_count = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
        trig_count = conn.execute("SELECT COUNT(*) as c FROM custom_triggers").fetchone()["c"]
        habits = conn.execute(
            "SELECT action_key, count, last_used FROM habit_stats ORDER BY count DESC LIMIT 6"
        ).fetchall()
        total_actions = sum(h["count"] for h in habits)

    xp = (mem_count * 25) + (trig_count * 40) + (total_actions * 5)
    level = max(1, 1 + (xp // 100))
    next_level_xp = level * 100

    return {
        "level": level,
        "xp": xp,
        "next_level_xp": next_level_xp,
        "progress_percent": min(100, int((xp % 100))),
        "memories_count": mem_count,
        "triggers_count": trig_count,
        "total_actions_learned": total_actions,
        "top_habits": [dict(h) for h in habits],
        "memories": list_memories(30),
        "triggers": list_custom_triggers(),
    }


def get_memory_context_for_prompt() -> str:
    """Format learned memories and top habits to inject into LLM system prompts."""
    memories = list_memories(12)
    triggers = list_custom_triggers()[:6]
    parts: List[str] = []
    if memories:
        mem_lines = [f"- [{m['category']}] {m['fact']}" for m in memories]
        parts.append("MEMÓRIA DE LONGO PRAZO DO USUÁRIO:\n" + "\n".join(mem_lines))
    if triggers:
        trig_lines = [f"- '{t['phrase']}' -> executa '{t['action_command']}'" for t in triggers]
        parts.append("ATALHOS APRENDIDOS DO USUÁRIO:\n" + "\n".join(trig_lines))
    return "\n\n".join(parts)

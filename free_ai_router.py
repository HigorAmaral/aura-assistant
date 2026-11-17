import re
import time
from typing import Dict, Any, List, Optional
import httpx
from storage import get_settings, log_activity

# Pool of Free AI Models ordered by priority for automatic failover
FREE_AI_POOL: List[Dict[str, Any]] = [
    {
        "id": "free:openai",
        "name": "GPT-4o Mini (Free Pool #1)",
        "provider": "Pollinations Free Cloud",
        "model_slug": "openai",
        "requires_key": False,
        "specialty": "Orquestração Geral & Diálogo",
    },
    {
        "id": "free:mistral",
        "name": "Mistral Small 3 (Free Pool #2)",
        "provider": "Pollinations Free Cloud",
        "model_slug": "mistral",
        "requires_key": False,
        "specialty": "Pesquisa Rápida & Síntese",
    },
    {
        "id": "free:qwen-coder",
        "name": "Qwen 2.5 Coder 32B (Free Pool #3)",
        "provider": "Pollinations Free Cloud",
        "model_slug": "qwen-coder",
        "requires_key": False,
        "specialty": "Código, Scripts & Sistema",
    },
    {
        "id": "free:deepseek",
        "name": "DeepSeek R1/V3 (Free Pool #4)",
        "provider": "Pollinations Free Cloud",
        "model_slug": "deepseek",
        "requires_key": False,
        "specialty": "Raciocínio Profundo & Estratégia",
    },
    {
        "id": "gemini:gemini-3.8-flash",
        "name": "Gemini 3.8 Flash (Google Free Tier)",
        "provider": "Google AI Studio",
        "model_slug": "gemini-3.8-flash",
        "requires_key": True,
        "key_setting": "gemini_api_key",
        "specialty": "Agente Multimodal & Function Calling",
    },
    {
        "id": "groq:llama-3.3-70b",
        "name": "Llama 3.3 70B (Groq Free Tier)",
        "provider": "Groq Cloud",
        "model_slug": "llama-3.3-70b-versatile",
        "requires_key": True,
        "key_setting": "groq_api_key",
        "specialty": "Ultra-Baixa Latência",
    },
    {
        "id": "openrouter:free",
        "name": "Gemma 3 / Llama 3.3 (:free)",
        "provider": "OpenRouter Free",
        "model_slug": "meta-llama/llama-3.3-70b-instruct:free",
        "requires_key": True,
        "key_setting": "openrouter_api_key",
        "specialty": "Rotação Open-Weight",
    },
    {
        "id": "cerebras:llama-3.3-70b",
        "name": "Llama 3.3 70B (Cerebras Free Tier)",
        "provider": "Cerebras Cloud",
        "model_slug": "llama-3.3-70b",
        "requires_key": True,
        "key_setting": "cerebras_api_key",
        "specialty": "Velocidade Extrema (2000+ tok/s)",
    },
    {
        "id": "deepseek:chat",
        "name": "DeepSeek V3/Chat (API Oficial)",
        "provider": "DeepSeek API",
        "model_slug": "deepseek-chat",
        "requires_key": True,
        "key_setting": "deepseek_api_key",
        "specialty": "Código & Raciocínio Avançado",
    },
    {
        "id": "custom:openai",
        "name": "Custom OpenAI-Compatible API",
        "provider": "Custom Endpoint",
        "model_slug": "gpt-4o-mini",
        "requires_key": True,
        "key_setting": "custom_openai_url",
        "specialty": "LM Studio / vLLM / Together / Custom",
    },
    {
        "id": "ollama:local",
        "name": "Ollama Local (Offline)",
        "provider": "Localhost GPU/CPU",
        "model_slug": "llama3.2",
        "requires_key": False,
        "specialty": "Privacidade 100% Local",
    },
]

# Runtime telemetry and cooldown tracking for automatic token/quota rotation
_PROVIDER_STATE: Dict[str, Dict[str, Any]] = {
    p["id"]: {
        "status": "online",
        "cooldown_until": 0.0,
        "success_count": 0,
        "failover_count": 0,
        "tokens_used": 0,
        "last_error": "",
    }
    for p in FREE_AI_POOL
}


def get_free_pool_status() -> List[Dict[str, Any]]:
    """Return real-time health, token usage, and cooldown status of all Free AI models."""
    now = time.time()
    settings = get_settings()
    out: List[Dict[str, Any]] = []

    for item in FREE_AI_POOL:
        pid = item["id"]
        st = _PROVIDER_STATE[pid]
        in_cooldown = now < st["cooldown_until"]
        has_key = True
        if item.get("requires_key"):
            key_name = item.get("key_setting", "")
            has_key = bool(str(settings.get(key_name, "")).strip())

        if not has_key:
            status_label = "aguardando_chave"
        elif in_cooldown:
            status_label = "rotacionado_quota"
        else:
            status_label = "ativo"

        out.append(
            {
                **item,
                "status": status_label,
                "cooldown_seconds_left": max(0, int(st["cooldown_until"] - now)),
                "success_count": st["success_count"],
                "failover_count": st["failover_count"],
                "tokens_used": st["tokens_used"],
                "last_error": st["last_error"],
            }
        )
    return out


def _clean_model_reply(text: str) -> str:
    """Strip internal <think>...</think> reasoning blocks if a reasoning model emits them."""
    if not text:
        return ""
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    return cleaned or text.strip()


def _resolve_task_config(task_type: str, preferred_model_id: Optional[str]) -> tuple[float, List[str]]:
    """Return optimal (temperature, priority_model_ids) for a given cognitive task type."""
    t = (task_type or "general").lower()
    if t in ("planning", "json", "audit"):
        temp = 0.2
        order = ["free:deepseek", "groq:llama-3.3-70b", "gemini:gemini-3.8-flash", "free:openai"]
    elif t in ("coding", "code", "debug"):
        temp = 0.25
        order = ["free:qwen-coder", "free:deepseek", "groq:llama-3.3-70b", "free:openai"]
    elif t in ("synthesis", "executive"):
        temp = 0.35
        order = ["free:deepseek", "free:openai", "free:mistral", "groq:llama-3.3-70b"]
    elif t in ("research", "web"):
        temp = 0.35
        order = ["free:mistral", "free:openai", "free:deepseek"]
    else:
        temp = 0.45
        order = []

    if preferred_model_id and preferred_model_id not in order:
        order = [preferred_model_id] + order
    elif preferred_model_id and t == "general":
        order = [preferred_model_id]
    return temp, order


_HTTP_POOL: Optional[httpx.Client] = None


def _get_http_client() -> httpx.Client:
    """Shared connection-pooled httpx.Client to avoid TCP/TLS handshake overhead per request."""
    global _HTTP_POOL
    if _HTTP_POOL is None or _HTTP_POOL.is_closed:
        _HTTP_POOL = httpx.Client(
            timeout=22.0,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _HTTP_POOL


def _call_openai_compatible(
    url: str,
    model_slug: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.45,
    api_key: str = "",
    provider_label: str = "Provider",
    timeout: float = 20.0,
) -> str:
    """Unified caller for OpenAI-compatible chat completion APIs (Pollinations, Groq, OpenRouter, Cerebras, DeepSeek, Custom)."""
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model_slug,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    client = _get_http_client()
    resp = client.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code == 429 or resp.status_code >= 500:
        raise RuntimeError(f"{provider_label} HTTP {resp.status_code} (Limite/Indisponível)")
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices", [])
    if choices and choices[0].get("message", {}).get("content"):
        return _clean_model_reply(choices[0]["message"]["content"])
    raise RuntimeError(f"Resposta vazia de {provider_label}")


def _call_pollinations_free(model_slug: str, system_prompt: str, user_prompt: str, temperature: float = 0.45) -> str:
    """Call Pollinations Free OpenAI-compatible endpoint (zero API key required)."""
    return _call_openai_compatible(
        url="https://text.pollinations.ai/openai",
        model_slug=model_slug,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        provider_label="Pollinations",
        timeout=22.0,
    )


def _call_groq_free(api_key: str, model_slug: str, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
    return _call_openai_compatible(
        url="https://api.groq.com/openai/v1/chat/completions",
        model_slug=model_slug,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        api_key=api_key,
        provider_label="Groq",
        timeout=18.0,
    )


def _call_openrouter_free(api_key: str, model_slug: str, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
    return _call_openai_compatible(
        url="https://openrouter.ai/api/v1/chat/completions",
        model_slug=model_slug,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        api_key=api_key,
        provider_label="OpenRouter",
        timeout=20.0,
    )


def _call_ollama_local(ollama_url: str, model_slug: str, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
    client = _get_http_client()
    resp = client.post(
        f"{ollama_url.rstrip('/')}/api/chat",
        json={
            "model": model_slug,
            "stream": False,
            "options": {"temperature": temperature},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=16.0,
    )
    resp.raise_for_status()
    return _clean_model_reply(resp.json().get("message", {}).get("content", ""))


def call_with_free_ai_failover(
    user_prompt: str,
    system_prompt: str,
    preferred_model_id: Optional[str] = None,
    task_type: str = "general",
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Execute prompt using the Free AI Pool with task-aware routing & automatic failover.
    """
    settings = get_settings()
    now = time.time()
    auto_temp, priority_ids = _resolve_task_config(task_type, preferred_model_id)
    eff_temp = auto_temp if temperature is None else temperature

    # Build candidate queue: priority_ids first, then remaining pool models
    pool_by_id = {p["id"]: p for p in FREE_AI_POOL}
    ordered_pool: List[Dict[str, Any]] = []
    for pid in priority_ids:
        if pid in pool_by_id and pool_by_id[pid] not in ordered_pool:
            ordered_pool.append(pool_by_id[pid])
    for p in FREE_AI_POOL:
        if p not in ordered_pool:
            ordered_pool.append(p)

    failover_chain: List[str] = []

    for candidate in ordered_pool:
        pid = candidate["id"]
        state = _PROVIDER_STATE[pid]

        # Skip if in cooldown (unless it's the only one)
        if now < state["cooldown_until"]:
            failover_chain.append(f"{candidate['name']} (em cooldown de quota)")
            continue

        # Check if key is required
        if candidate.get("requires_key"):
            key_val = str(settings.get(candidate.get("key_setting", ""), "")).strip()
            if not key_val:
                continue
        else:
            key_val = ""

        try:
            if pid.startswith("free:"):
                reply = _call_pollinations_free(candidate["model_slug"], system_prompt, user_prompt, temperature=eff_temp)
            elif pid.startswith("gemini:"):
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=key_val)
                gemini_model = settings.get("gemini_model") or "gemini-2.5-flash"
                try:
                    resp = client.models.generate_content(
                        model=gemini_model,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            temperature=eff_temp,
                        ),
                    )
                    reply = _clean_model_reply(resp.text or "")
                except Exception:
                    inter = client.interactions.create(
                        model=gemini_model,
                        input=user_prompt,
                        system_instruction=system_prompt,
                    )
                    reply = _clean_model_reply(inter.output_text or "")
            elif pid.startswith("groq:"):
                reply = _call_groq_free(key_val, candidate["model_slug"], system_prompt, user_prompt, temperature=eff_temp)
            elif pid.startswith("openrouter:"):
                reply = _call_openrouter_free(key_val, candidate["model_slug"], system_prompt, user_prompt, temperature=eff_temp)
            elif pid.startswith("cerebras:"):
                reply = _call_openai_compatible(
                    url="https://api.cerebras.ai/v1/chat/completions",
                    model_slug=candidate["model_slug"],
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=eff_temp,
                    api_key=key_val,
                    provider_label="Cerebras",
                    timeout=15.0,
                )
            elif pid.startswith("deepseek:"):
                reply = _call_openai_compatible(
                    url="https://api.deepseek.com/chat/completions",
                    model_slug=candidate["model_slug"],
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=eff_temp,
                    api_key=key_val,
                    provider_label="DeepSeek",
                    timeout=20.0,
                )
            elif pid == "custom:openai":
                custom_url = str(settings.get("custom_openai_url", "")).strip()
                custom_key = str(settings.get("custom_openai_key", "")).strip()
                custom_model = str(settings.get("custom_openai_model", "")).strip() or candidate["model_slug"]
                if not custom_url:
                    continue
                endpoint = custom_url.rstrip("/")
                if not endpoint.endswith("/chat/completions"):
                    endpoint = f"{endpoint}/chat/completions"
                reply = _call_openai_compatible(
                    url=endpoint,
                    model_slug=custom_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=eff_temp,
                    api_key=custom_key,
                    provider_label="Custom API",
                    timeout=22.0,
                )
            elif pid == "ollama:local":
                reply = _call_ollama_local(
                    settings.get("ollama_url", "http://localhost:11434"),
                    settings.get("ollama_model", "llama3.2"),
                    system_prompt,
                    user_prompt,
                    temperature=eff_temp,
                )
            else:
                continue

            if reply:
                est_tokens = max(15, (len(user_prompt) + len(reply)) // 4)
                state["success_count"] += 1
                state["tokens_used"] += est_tokens
                state["status"] = "online"
                if failover_chain:
                    log_activity(
                        "FAILOVER IA",
                        f"Rotacionado automaticamente para {candidate['name']} após limite em {len(failover_chain)} provedor(es)",
                    )
                return {
                    "success": True,
                    "reply": reply,
                    "model_id": pid,
                    "provider_name": candidate["name"],
                    "failover_chain": failover_chain,
                    "tokens_estimated": est_tokens,
                }
        except Exception as e:
            err_str = str(e)
            # Pollinations shares one 45s IP rate limit across all free:* models:
            # if one returns 402/429, put all free:* Pollinations models in 45s cooldown immediately.
            cooldown_sec = 45.0 if ("402" in err_str or "429" in err_str or "FREE_LIMIT" in err_str) else 60.0
            if pid.startswith("free:") and ("402" in err_str or "429" in err_str or "FREE_LIMIT" in err_str):
                for p_id, p_st in _PROVIDER_STATE.items():
                    if p_id.startswith("free:"):
                        p_st["failover_count"] += 1
                        p_st["cooldown_until"] = time.time() + cooldown_sec
                        p_st["last_error"] = "Limite IP gratuito Pollinations (45s)"
            else:
                state["failover_count"] += 1
                state["cooldown_until"] = time.time() + cooldown_sec
                state["last_error"] = err_str[:120]
            failover_chain.append(f"{candidate['name']} -> {err_str[:45]}")
            continue

    return {
        "success": False,
        "reply": "",
        "model_id": "aura:local",
        "provider_name": "AURA Neural Local (Offline)",
        "failover_chain": failover_chain,
        "tokens_estimated": 0,
    }

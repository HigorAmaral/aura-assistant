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


def _call_pollinations_free(model_slug: str, system_prompt: str, user_prompt: str) -> str:
    """Call Pollinations Free OpenAI-compatible endpoint (zero API key required)."""
    url = "https://text.pollinations.ai/openai"
    payload = {
        "model": model_slug,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.6,
    }
    with httpx.Client(timeout=18.0, follow_redirects=True) as client:
        resp = client.post(url, json=payload)
        if resp.status_code == 429 or resp.status_code >= 500:
            raise RuntimeError(f"HTTP {resp.status_code} (Limite de tokens/requisições atingido)")
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        if choices and choices[0].get("message", {}).get("content"):
            return choices[0]["message"]["content"].strip()
        raise RuntimeError("Resposta vazia do provedor gratuito")


def _call_groq_free(api_key: str, model_slug: str, system_prompt: str, user_prompt: str) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model_slug,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    with httpx.Client(timeout=16.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code == 429:
            raise RuntimeError("Groq 429 Quota Exceeded")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


def _call_openrouter_free(api_key: str, model_slug: str, system_prompt: str, user_prompt: str) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model_slug,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    with httpx.Client(timeout=18.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code == 429:
            raise RuntimeError("OpenRouter 429 Quota Exceeded")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


def _call_ollama_local(ollama_url: str, model_slug: str, system_prompt: str, user_prompt: str) -> str:
    with httpx.Client(timeout=12.0) as client:
        resp = client.post(
            f"{ollama_url.rstrip('/')}/api/chat",
            json={
                "model": model_slug,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "").strip()


def call_with_free_ai_failover(
    user_prompt: str,
    system_prompt: str,
    preferred_model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute prompt using the Free AI Pool. If the first model runs out of tokens,
    hits a rate-limit (429), or times out, automatically rotate to the next available
    free model in the queue!
    """
    settings = get_settings()
    now = time.time()

    # Build candidate queue starting with preferred_model_id (if specified) followed by the rest of the pool
    ordered_pool: List[Dict[str, Any]] = []
    if preferred_model_id:
        for p in FREE_AI_POOL:
            if p["id"] == preferred_model_id:
                ordered_pool.append(p)
                break
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
                reply = _call_pollinations_free(candidate["model_slug"], system_prompt, user_prompt)
            elif pid.startswith("gemini:"):
                from google import genai
                client = genai.Client(api_key=key_val)
                inter = client.interactions.create(
                    model="gemini-3.8-flash",
                    input=user_prompt,
                    system_instruction=system_prompt,
                )
                reply = inter.output_text or ""
            elif pid.startswith("groq:"):
                reply = _call_groq_free(key_val, candidate["model_slug"], system_prompt, user_prompt)
            elif pid.startswith("openrouter:"):
                reply = _call_openrouter_free(key_val, candidate["model_slug"], system_prompt, user_prompt)
            elif pid == "ollama:local":
                reply = _call_ollama_local(
                    settings.get("ollama_url", "http://localhost:11434"),
                    settings.get("ollama_model", "llama3.2"),
                    system_prompt,
                    user_prompt,
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

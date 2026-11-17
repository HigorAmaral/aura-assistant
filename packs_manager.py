import ast
import base64
import hashlib
import math
import operator
import secrets
import string
import time
import urllib.parse
import uuid
from typing import Any, Dict, List, Optional

import httpx

from storage import get_settings, update_settings, list_tasks, list_notes, log_activity

# Shared HTTP client with connection pooling for external pack APIs
_PACK_HTTP: Optional[httpx.Client] = None
_PACK_CACHE: Dict[str, Dict[str, Any]] = {}


def _http() -> httpx.Client:
    global _PACK_HTTP
    if _PACK_HTTP is None or _PACK_HTTP.is_closed:
        _PACK_HTTP = httpx.Client(
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": "AURA-OS/5.1 (+https://github.com/HigorAmaral/aura-assistant)"},
        )
    return _PACK_HTTP


def _cache_get(key: str, ttl_sec: float) -> Optional[Any]:
    entry = _PACK_CACHE.get(key)
    if entry and (time.monotonic() - entry["ts"]) < ttl_sec:
        return entry["data"]
    return None


def _cache_set(key: str, data: Any) -> None:
    _PACK_CACHE[key] = {"ts": time.monotonic(), "data": data}
    if len(_PACK_CACHE) > 120:
        oldest_key = min(_PACK_CACHE, key=lambda k: _PACK_CACHE[k]["ts"])
        _PACK_CACHE.pop(oldest_key, None)


PACKS_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "weather",
        "name": "Clima & Previsão (Open-Meteo)",
        "description": "Previsão do tempo em tempo real, temperatura, vento, umidade e próximos dias para qualquer cidade.",
        "requires_key": False,
        "actions": ["forecast"],
        "category": "Dados em Tempo Real",
    },
    {
        "id": "finance",
        "name": "Finanças & Cripto (AwesomeAPI + CoinGecko)",
        "description": "Cotações em tempo real de Dólar (USD), Euro (EUR), Bitcoin (BTC), Ethereum (ETH) e variação diária.",
        "requires_key": False,
        "actions": ["quotes"],
        "category": "Dados em Tempo Real",
    },
    {
        "id": "news",
        "name": "Notícias & Tech (TabNews + Hacker News)",
        "description": "Manchetes de tecnologia e programação em português (TabNews) e globais (Hacker News).",
        "requires_key": False,
        "actions": ["headlines"],
        "category": "Dados em Tempo Real",
    },
    {
        "id": "translate",
        "name": "Tradutor Universal (MyMemory API)",
        "description": "Tradução instantânea entre Português, Inglês, Espanhol, Francês, Alemão, Italiano e Japonês.",
        "requires_key": False,
        "actions": ["translate"],
        "category": "Idiomas & Texto",
    },
    {
        "id": "dev_utils",
        "name": "Dev Utils & Segurança",
        "description": "IP público & geolocalização, gerador de senhas fortes, UUID v4, hash SHA256/MD5, Base64, calculadora segura e QR Code.",
        "requires_key": False,
        "actions": ["public_ip", "password", "uuid", "hash", "base64_encode", "base64_decode", "calc", "qr"],
        "category": "Ferramentas Dev",
    },
    {
        "id": "productivity",
        "name": "Briefing Diário & Produtividade",
        "description": "Resumo executivo unificado com suas tarefas pendentes, notas, status do PC, clima e cotações.",
        "requires_key": False,
        "actions": ["daily_briefing"],
        "category": "Produtividade",
    },
]


def is_pack_enabled(pack_id: str) -> bool:
    enabled_map = get_settings().get("enabled_packs") or {}
    return bool(enabled_map.get(pack_id, True))


def list_packs() -> List[Dict[str, Any]]:
    enabled_map = get_settings().get("enabled_packs") or {}
    return [
        {**pack, "enabled": bool(enabled_map.get(pack["id"], True))}
        for pack in PACKS_CATALOG
    ]


def toggle_pack(pack_id: str, enabled: Optional[bool] = None) -> Dict[str, Any]:
    valid_ids = {p["id"] for p in PACKS_CATALOG}
    if pack_id not in valid_ids:
        return {"ok": False, "error": f"Pack '{pack_id}' não encontrado."}
    settings = get_settings()
    enabled_map = dict(settings.get("enabled_packs") or {})
    new_val = (not bool(enabled_map.get(pack_id, True))) if enabled is None else bool(enabled)
    enabled_map[pack_id] = new_val
    update_settings({"enabled_packs": enabled_map})
    log_activity("PACKS", f"Pack '{pack_id}' {'ativado' if new_val else 'desativado'}")
    return {"ok": True, "pack_id": pack_id, "enabled": new_val, "packs": list_packs()}


# --- 1. Weather Pack (Open-Meteo) ---
_WMO_CODES_PT = {
    0: "Céu limpo",
    1: "Predominantemente limpo",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Nevoeiro",
    48: "Nevoeiro com geada",
    51: "Garoa leve",
    53: "Garoa moderada",
    55: "Garoa intensa",
    61: "Chuva leve",
    63: "Chuva moderada",
    65: "Chuva forte",
    71: "Neve leve",
    80: "Pancadas de chuva leves",
    81: "Pancadas de chuva moderadas",
    82: "Pancadas de chuva fortes",
    95: "Tempestade com trovoadas",
}


def get_weather(city: str = "São Paulo") -> Dict[str, Any]:
    city_clean = (city or "São Paulo").strip()
    cache_key = f"weather:{city_clean.lower()}"
    cached = _cache_get(cache_key, ttl_sec=180.0)
    if cached:
        return cached

    try:
        geo = _http().get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city_clean, "count": 1, "language": "pt", "format": "json"},
        )
        geo.raise_for_status()
        results = geo.json().get("results") or []
        if not results:
            return {"ok": False, "error": f"Cidade '{city_clean}' não encontrada."}

        loc = results[0]
        lat, lon = loc["latitude"], loc["longitude"]
        place_label = f"{loc.get('name', city_clean)}, {loc.get('admin1', '')} ({loc.get('country_code', '')})".replace(",  (", " (")

        fc = _http().get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                "timezone": "auto",
                "forecast_days": 3,
            },
        )
        fc.raise_for_status()
        data = fc.json()
        cur = data.get("current", {})
        daily = data.get("daily", {})

        wcode = int(cur.get("weather_code", 0))
        condition = _WMO_CODES_PT.get(wcode, f"Código {wcode}")
        forecast_days = []
        dates = daily.get("time", [])
        for i, dt in enumerate(dates[:3]):
            dcode = int((daily.get("weather_code") or [0])[i])
            forecast_days.append(
                {
                    "date": dt,
                    "temp_max": (daily.get("temperature_2m_max") or [None])[i],
                    "temp_min": (daily.get("temperature_2m_min") or [None])[i],
                    "rain_prob": (daily.get("precipitation_probability_max") or [0])[i],
                    "condition": _WMO_CODES_PT.get(dcode, "Variável"),
                }
            )

        out = {
            "ok": True,
            "location": place_label,
            "temperature_c": cur.get("temperature_2m"),
            "feels_like_c": cur.get("apparent_temperature"),
            "humidity_percent": cur.get("relative_humidity_2m"),
            "wind_kmh": cur.get("wind_speed_10m"),
            "condition": condition,
            "forecast": forecast_days,
        }
        _cache_set(cache_key, out)
        return out
    except Exception as exc:
        return {"ok": False, "error": f"Falha ao consultar clima: {exc}"}


# --- 2. Finance & Crypto Pack ---
def get_finance_quotes(pairs: str = "USD-BRL,EUR-BRL,BTC-BRL,ETH-BRL") -> Dict[str, Any]:
    pairs_clean = (pairs or "USD-BRL,EUR-BRL,BTC-BRL,ETH-BRL").upper().replace(" ", "")
    cache_key = f"finance:{pairs_clean}"
    cached = _cache_get(cache_key, ttl_sec=60.0)
    if cached:
        return cached

    quotes: List[Dict[str, Any]] = []
    try:
        resp = _http().get(f"https://economia.awesomeapi.com.br/json/last/{pairs_clean}")
        resp.raise_for_status()
        raw = resp.json()
        for _, item in raw.items():
            quotes.append(
                {
                    "pair": f"{item.get('code')}/{item.get('codein')}",
                    "name": item.get("name", ""),
                    "bid": float(item.get("bid", 0)),
                    "high": float(item.get("high", 0)),
                    "low": float(item.get("low", 0)),
                    "pct_change": float(item.get("pctChange", 0)),
                    "updated_at": item.get("create_date", ""),
                }
            )
        out = {"ok": True, "source": "AwesomeAPI", "quotes": quotes}
        _cache_set(cache_key, out)
        return out
    except Exception as exc:
        return {"ok": False, "error": f"Falha ao consultar cotações: {exc}", "quotes": []}


# --- 3. Tech News Pack ---
def get_tech_news(topic: str = "pt", limit: int = 6) -> Dict[str, Any]:
    topic_norm = (topic or "pt").lower().strip()
    limit = max(1, min(int(limit), 12))
    cache_key = f"news:{topic_norm}:{limit}"
    cached = _cache_get(cache_key, ttl_sec=120.0)
    if cached:
        return cached

    items: List[Dict[str, Any]] = []
    try:
        if topic_norm in ("hn", "hackernews", "global", "en"):
            ids_resp = _http().get("https://hacker-news.firebaseio.com/v0/topstories.json")
            ids_resp.raise_for_status()
            story_ids = ids_resp.json()[:limit]
            for sid in story_ids:
                s_resp = _http().get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
                if s_resp.status_code == 200:
                    st = s_resp.json() or {}
                    items.append(
                        {
                            "title": st.get("title", "Sem título"),
                            "url": st.get("url") or f"https://news.ycombinator.com/item?id={sid}",
                            "score": st.get("score", 0),
                            "source": "Hacker News",
                        }
                    )
        else:
            resp = _http().get(
                "https://www.tabnews.com.br/api/v1/contents",
                params={"strategy": "relevant", "per_page": limit},
            )
            resp.raise_for_status()
            for post in resp.json():
                owner = post.get("owner_username", "")
                slug = post.get("slug", "")
                items.append(
                    {
                        "title": post.get("title", "Sem título"),
                        "url": f"https://www.tabnews.com.br/{owner}/{slug}",
                        "score": post.get("tabcoins", 0),
                        "source": "TabNews",
                    }
                )
        out = {"ok": True, "topic": topic_norm, "items": items}
        _cache_set(cache_key, out)
        return out
    except Exception as exc:
        return {"ok": False, "error": f"Falha ao buscar notícias: {exc}", "items": []}


# --- 4. Translate Pack ---
_LANG_ALIASES = {
    "portugues": "pt", "português": "pt", "pt-br": "pt", "pt": "pt",
    "ingles": "en", "inglês": "en", "english": "en", "en": "en",
    "espanhol": "es", "spanish": "es", "es": "es",
    "frances": "fr", "francês": "fr", "french": "fr", "fr": "fr",
    "alemao": "de", "alemão": "de", "german": "de", "de": "de",
    "italiano": "it", "italian": "it", "it": "it",
    "japones": "ja", "japonês": "ja", "japanese": "ja", "ja": "ja",
}


def translate_text(text: str, target_lang: str = "en", source_lang: str = "pt") -> Dict[str, Any]:
    clean_text = (text or "").strip()
    if not clean_text:
        return {"ok": False, "error": "Texto vazio para tradução."}
    src = _LANG_ALIASES.get(source_lang.lower().strip(), source_lang.lower().strip()[:2] or "pt")
    tgt = _LANG_ALIASES.get(target_lang.lower().strip(), target_lang.lower().strip()[:2] or "en")
    if src == tgt:
        src = "en" if tgt == "pt" else "pt"

    try:
        resp = _http().get(
            "https://api.mymemory.translated.net/get",
            params={"q": clean_text[:500], "langpair": f"{src}|{tgt}"},
        )
        resp.raise_for_status()
        data = resp.json()
        translated = (data.get("responseData") or {}).get("translatedText", "")
        if not translated:
            return {"ok": False, "error": "Não foi possível traduzir o texto."}
        return {
            "ok": True,
            "source_lang": src,
            "target_lang": tgt,
            "original": clean_text,
            "translated": translated,
        }
    except Exception as exc:
        return {"ok": False, "error": f"Erro na API de tradução: {exc}"}


# --- 5. Dev Utils Pack ---
_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_calculate(expr: str) -> Dict[str, Any]:
    """Safely evaluate basic arithmetic expressions using AST (no eval)."""
    cleaned = (expr or "").strip().replace(",", ".").replace("^", "**").replace("x", "*")
    cleaned = cleaned.replace("×", "*").replace("÷", "/")
    if not cleaned or len(cleaned) > 120:
        return {"ok": False, "error": "Expressão inválida ou muito longa."}

    def _eval_node(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
            left = _eval_node(node.left)
            right = _eval_node(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("Expoente muito grande")
            return _SAFE_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
            return _SAFE_OPS[type(node.op)](_eval_node(node.operand))
        raise ValueError("Operação não suportada")

    try:
        tree = ast.parse(cleaned, mode="eval")
        val = _eval_node(tree)
        if math.isfinite(val) and val.is_integer():
            display = int(val)
        else:
            display = round(val, 6)
        return {"ok": True, "expression": expr, "result": display}
    except Exception as exc:
        return {"ok": False, "error": f"Não foi possível calcular '{expr}': {exc}"}


def run_dev_util(action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    p = params or {}
    act = (action or "").lower().strip()

    if act == "password":
        length = max(8, min(int(p.get("length", 16)), 64))
        alphabet = string.ascii_letters + string.digits + "!@#$%&*-_"
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        return {"ok": True, "action": "password", "result": pwd, "length": length}

    if act == "uuid":
        return {"ok": True, "action": "uuid", "result": str(uuid.uuid4())}

    if act == "hash":
        text = str(p.get("text", ""))
        algo = str(p.get("algo", "sha256")).lower()
        if algo not in ("md5", "sha1", "sha256", "sha512"):
            algo = "sha256"
        digest = getattr(hashlib, algo)(text.encode("utf-8")).hexdigest()
        return {"ok": True, "action": "hash", "algo": algo, "result": digest}

    if act == "base64_encode":
        text = str(p.get("text", ""))
        encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
        return {"ok": True, "action": "base64_encode", "result": encoded}

    if act == "base64_decode":
        text = str(p.get("text", ""))
        try:
            decoded = base64.b64decode(text.encode("ascii")).decode("utf-8", errors="replace")
            return {"ok": True, "action": "base64_decode", "result": decoded}
        except Exception as exc:
            return {"ok": False, "error": f"Base64 inválido: {exc}"}

    if act == "calc":
        return safe_calculate(str(p.get("expression", "")))

    if act == "qr":
        data = str(p.get("data", "")).strip()
        if not data:
            return {"ok": False, "error": "Informe o texto ou URL para gerar o QR Code."}
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=240x240&data={urllib.parse.quote(data)}"
        return {"ok": True, "action": "qr", "data": data, "qr_image_url": qr_url}

    if act == "public_ip":
        try:
            resp = _http().get("https://ipwho.is/")
            resp.raise_for_status()
            d = resp.json()
            return {
                "ok": True,
                "action": "public_ip",
                "ip": d.get("ip", ""),
                "city": d.get("city", ""),
                "region": d.get("region", ""),
                "country": d.get("country", ""),
                "isp": (d.get("connection") or {}).get("isp", ""),
            }
        except Exception as exc:
            return {"ok": False, "error": f"Falha ao obter IP público: {exc}"}

    return {"ok": False, "error": f"Utilitário '{action}' desconhecido."}


# --- 6. Productivity / Daily Briefing Pack ---
def get_daily_briefing(city: str = "São Paulo") -> Dict[str, Any]:
    from system_tools import get_system_stats

    tasks = list_tasks(include_done=False)
    notes = list_notes()[:5]
    stats = get_system_stats()
    weather = get_weather(city) if is_pack_enabled("weather") else {"ok": False}
    finance = get_finance_quotes("USD-BRL,EUR-BRL,BTC-BRL") if is_pack_enabled("finance") else {"ok": False}

    return {
        "ok": True,
        "pending_tasks_count": len(tasks),
        "top_tasks": tasks[:5],
        "recent_notes_count": len(notes),
        "system": {
            "cpu_percent": stats["cpu"]["percent"],
            "ram_percent": stats["ram"]["percent"],
            "disk_free_gb": stats["disk"]["free_gb"],
            "uptime": stats["os"]["uptime"],
        },
        "weather": weather if weather.get("ok") else None,
        "finance": finance.get("quotes") if finance.get("ok") else None,
    }


def run_pack_action(pack_id: str, action: str = "", params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not is_pack_enabled(pack_id):
        return {"ok": False, "error": f"O pack '{pack_id}' está desativado nas configurações."}

    p = params or {}
    if pack_id == "weather":
        return get_weather(city=str(p.get("city", "São Paulo")))
    if pack_id == "finance":
        return get_finance_quotes(pairs=str(p.get("pairs", "USD-BRL,EUR-BRL,BTC-BRL,ETH-BRL")))
    if pack_id == "news":
        return get_tech_news(topic=str(p.get("topic", "pt")), limit=int(p.get("limit", 6)))
    if pack_id == "translate":
        return translate_text(
            text=str(p.get("text", "")),
            target_lang=str(p.get("target_lang", "en")),
            source_lang=str(p.get("source_lang", "pt")),
        )
    if pack_id == "dev_utils":
        return run_dev_util(action=action or str(p.get("action", "uuid")), params=p)
    if pack_id == "productivity":
        return get_daily_briefing(city=str(p.get("city", "São Paulo")))

    return {"ok": False, "error": f"Pack '{pack_id}' não encontrado."}

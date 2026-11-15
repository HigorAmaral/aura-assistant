import re
import urllib.parse
from typing import Dict, Any, List
import httpx
from bs4 import BeautifulSoup
from storage import log_activity

HEADERS = {
    "User-Agent": (
        "AURA-OS/5.0 (https://github.com/aura-assistant; contact@aura-os.local) "
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _extract_wiki_topic(query: str) -> str:
    """Strip Portuguese conversational question prefixes so Wikipedia finds the exact entity."""
    q = query.strip().rstrip("?!.")
    q = re.sub(
        r"^(?:aura[,\s]+)?(?:o\s+que\s+[eé]|o\s+que\s+s[aã]o|quem\s+[eé]|quem\s+foi|"
        r"me\s+fale\s+sobre|fale\s+sobre|explique(?:\s+o\s+que\s+[eé])?|"
        r"defina|significado\s+de|pesquise(?:\s+sobre)?|busque(?:\s+sobre)?)\s+",
        "",
        q,
        flags=re.IGNORECASE,
    ).strip()
    q = re.sub(r"^(?:um|uma|uns|umas|o|a|os|as)\s+", "", q, flags=re.IGNORECASE).strip()
    return q or query.strip()


def search_wikipedia_pt(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """Fetch clean introductory extracts in Portuguese directly from Wikipedia PT API."""
    topic = _extract_wiki_topic(query)
    if not topic:
        return []
    out: List[Dict[str, str]] = []
    try:
        wiki_url = "https://pt.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": topic,
            "gsrlimit": max_results,
            "prop": "extracts",
            "exintro": 1,
            "explaintext": 1,
            "exsentences": 4,
            "format": "json",
        }
        with httpx.Client(headers=HEADERS, timeout=8.0) as client:
            r = client.get(wiki_url, params=params)
            if r.status_code == 200:
                pages = r.json().get("query", {}).get("pages", {})
                sorted_pages = sorted(pages.values(), key=lambda p: p.get("index", 999))
                for page in sorted_pages:
                    title = page.get("title", "").strip()
                    extract = page.get("extract", "").strip()
                    if title and extract:
                        page_url = f"https://pt.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                        out.append(
                            {
                                "title": f"{title} — Wikipédia",
                                "url": page_url,
                                "snippet": extract,
                            }
                        )
    except Exception:
        pass
    return out


def search_web(query: str, max_results: int = 6) -> Dict[str, Any]:
    """Perform a live web search via Wikipedia PT Extracts + DuckDuckGo HTML and return structured snippets."""
    q = query.strip()
    if not q:
        return {"success": False, "query": "", "results": [], "summary": "Consulta vazia."}

    results: List[Dict[str, str]] = []

    # 1. Check Wikipedia PT first when it looks like a knowledge/definition query
    is_definition_query = bool(
        re.match(
            r"^\s*(?:o\s+que|quem|como\s+funciona|defina|explique|significado)",
            q,
            re.IGNORECASE,
        )
    )
    if is_definition_query:
        results.extend(search_wikipedia_pt(q, max_results=2))

    # 2. Try DuckDuckGo HTML search (filtering ads and empty snippets)
    try:
        url = "https://html.duckduckgo.com/html/"
        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=10.0) as client:
            resp = client.post(url, data={"q": q, "kl": "br-pt"})
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for block in soup.select(".result"):
                    title_el = block.select_one(".result__a")
                    snippet_el = block.select_one(".result__snippet")
                    if not title_el:
                        continue
                    title = title_el.get_text(" ", strip=True)
                    raw_href = title_el.get("href", "")
                    if "uddg=" in raw_href:
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
                        link = parsed.get("uddg", [raw_href])[0]
                    else:
                        link = raw_href
                    snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
                    if (
                        not title
                        or not link
                        or not snippet
                        or "duckduckgo.com/y.js" in link
                        or "bing.com/aclick" in link
                    ):
                        continue
                    if not any(r["url"] == link for r in results):
                        results.append({"title": title, "url": link, "snippet": snippet})
                    if len(results) >= max_results:
                        break
    except Exception:
        pass

    # 3. Supplement with Wikipedia PT if not already fetched or if fewer than 3 results
    if not is_definition_query and len(results) < 3:
        for w_item in search_wikipedia_pt(q, max_results=2):
            if not any(r["url"] == w_item["url"] for r in results):
                results.append(w_item)
            if len(results) >= max_results:
                break

    log_activity("PESQUISA WEB", f"Pesquisa por '{q}' ({len(results)} resultados)")

    if not results:
        return {
            "success": False,
            "query": q,
            "results": [],
            "summary": f"Não consegui obter resultados externos agora para '{q}'.",
        }

    # Build a clean readable synthesis
    top_points = [f"• **{r['title']}**: {r['snippet']}" for r in results[:4] if r.get("snippet")]
    summary = f"Encontrei {len(results)} fontes para **{q}**:\n\n" + "\n".join(top_points)
    return {
        "success": True,
        "query": q,
        "results": results,
        "summary": summary,
    }


def read_and_summarize_url(url: str) -> Dict[str, Any]:
    """Fetch a webpage and extract its main readable content."""
    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        clean_url = "https://" + clean_url

    try:
        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=12.0) as client:
            resp = client.get(clean_url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
                tag.decompose()

            title = soup.title.get_text(strip=True) if soup.title else clean_url
            paragraphs = [
                p.get_text(" ", strip=True)
                for p in soup.find_all(["p", "h1", "h2", "h3", "li"])
                if len(p.get_text(strip=True)) > 40
            ]
            content = "\n\n".join(paragraphs[:20])
            if not content:
                content = soup.get_text(" ", strip=True)[:3500]
            else:
                content = content[:3500]

        log_activity("LEITURA WEB", f"Página lida: {title[:50]}")
        return {
            "success": True,
            "url": clean_url,
            "title": title,
            "excerpt": content,
        }
    except Exception as e:
        return {
            "success": False,
            "url": clean_url,
            "title": clean_url,
            "excerpt": f"Erro ao acessar a página: {e}",
        }

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).parent.resolve()


def _creation_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _run_gh(*args: str, timeout: int = 12) -> subprocess.CompletedProcess:
    gh_bin = shutil.which("gh") or "gh"
    return subprocess.run(
        [gh_bin, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_creation_flags(),
    )


def is_gh_available() -> bool:
    return shutil.which("gh") is not None


def get_github_profile() -> Dict[str, Any]:
    if not is_gh_available():
        return {"ok": False, "error": "GitHub CLI (gh) não está instalado no sistema."}
    try:
        res = _run_gh("api", "user", timeout=10)
        if res.returncode != 0:
            return {"ok": False, "error": res.stderr.strip() or "GitHub CLI não autenticado (execute: gh auth login)."}
        data = json.loads(res.stdout)
        return {
            "ok": True,
            "login": data.get("login", ""),
            "name": data.get("name") or data.get("login", ""),
            "url": data.get("html_url", ""),
            "public_repos": data.get("public_repos", 0),
            "total_private_repos": data.get("total_private_repos", 0),
            "followers": data.get("followers", 0),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def list_github_repos(limit: int = 12) -> Dict[str, Any]:
    if not is_gh_available():
        return {"ok": False, "error": "GitHub CLI (gh) não está instalado."}
    try:
        res = _run_gh(
            "repo",
            "list",
            "--limit",
            str(limit),
            "--json",
            "nameWithOwner,visibility,url,updatedAt,description,primaryLanguage",
            timeout=12,
        )
        if res.returncode != 0:
            return {"ok": False, "error": res.stderr.strip() or "Falha ao listar repositórios."}
        repos = json.loads(res.stdout or "[]")
        return {"ok": True, "repos": repos}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def inspect_github_repo(repo_slug: str) -> Dict[str, Any]:
    if not is_gh_available():
        return {"ok": False, "error": "GitHub CLI (gh) não está instalado."}
    try:
        slug = repo_slug.strip()
        if "/" not in slug:
            prof = get_github_profile()
            if prof.get("ok") and prof.get("login"):
                slug = f"{prof['login']}/{slug}"

        info_res = _run_gh(
            "repo",
            "view",
            slug,
            "--json",
            "nameWithOwner,description,url,visibility,defaultBranchRef,stargazerCount,updatedAt",
            timeout=12,
        )
        if info_res.returncode != 0:
            return {"ok": False, "error": info_res.stderr.strip() or f"Repositório '{slug}' não encontrado."}
        repo_info = json.loads(info_res.stdout)

        commits_res = _run_gh("api", f"repos/{slug}/commits?per_page=5", timeout=10)
        commits: List[Dict[str, str]] = []
        if commits_res.returncode == 0:
            for c in json.loads(commits_res.stdout or "[]"):
                c_obj = c.get("commit", {})
                commits.append({
                    "sha": str(c.get("sha", ""))[:7],
                    "message": str(c_obj.get("message", "")).splitlines()[0],
                    "date": str((c_obj.get("author") or {}).get("date", "")),
                })

        return {"ok": True, "repo": repo_info, "commits": commits}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def get_local_git_summary(cwd: Optional[str] = None) -> Dict[str, Any]:
    target_dir = cwd or str(BASE_DIR)
    if not shutil.which("git"):
        return {"ok": False, "error": "Git não encontrado no PATH."}
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=target_dir, capture_output=True, text=True, timeout=6, creationflags=_creation_flags(),
        )
        if branch.returncode != 0:
            return {"ok": False, "error": "Diretório atual não é um repositório Git."}
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=target_dir, capture_output=True, text=True, timeout=6, creationflags=_creation_flags(),
        )
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=target_dir, capture_output=True, text=True, timeout=6, creationflags=_creation_flags(),
        )
        log = subprocess.run(
            ["git", "log", "-3", "--oneline"],
            cwd=target_dir, capture_output=True, text=True, timeout=6, creationflags=_creation_flags(),
        )
        return {
            "ok": True,
            "branch": branch.stdout.strip(),
            "remote": remote.stdout.strip(),
            "status_lines": [line for line in status.stdout.splitlines() if line.strip()],
            "recent_commits": [line for line in log.stdout.splitlines() if line.strip()],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def format_github_context(prompt: str) -> Dict[str, Any]:
    """Fetch live GitHub profile, repos, and matching repo details for the user prompt."""
    profile = get_github_profile()
    if not profile.get("ok"):
        return {
            "ok": False,
            "summary": f"Não foi possível conectar ao GitHub CLI: {profile.get('error')}",
            "profile": profile,
        }

    repos_res = list_github_repos(limit=12)
    repos = repos_res.get("repos", []) if repos_res.get("ok") else []

    # Check if prompt mentions a specific repo name
    lower = prompt.lower()
    matched_repo_detail = None
    explicit_slug = re.search(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", prompt)
    if explicit_slug:
        matched_repo_detail = inspect_github_repo(explicit_slug.group(1))
    else:
        for r in repos:
            full_name = r.get("nameWithOwner", "")
            short_name = full_name.split("/")[-1].lower()
            if short_name and short_name in lower:
                matched_repo_detail = inspect_github_repo(full_name)
                break

    lines = [
        f"**GitHub Conectado:** `{profile['login']}` ({profile['name']}) — {profile['url']}",
        f"Repositórios públicos: **{profile['public_repos']}** | Privados: **{profile['total_private_repos']}**",
    ]
    if repos:
        lines.append("\n**Repositórios recentes:**")
        for r in repos[:10]:
            lang = (r.get("primaryLanguage") or {}).get("name") or "-"
            vis = r.get("visibility", "")
            desc = (r.get("description") or "").strip()
            desc_str = f" — {desc[:75]}" if desc else ""
            lines.append(f"- `{r['nameWithOwner']}` [{vis}, {lang}]{desc_str} ({r['url']})")

    if matched_repo_detail and matched_repo_detail.get("ok"):
        ri = matched_repo_detail["repo"]
        lines.append(f"\n**Detalhes de `{ri['nameWithOwner']}`:**")
        if ri.get("description"):
            lines.append(f"Descrição: {ri['description']}")
        commits = matched_repo_detail.get("commits", [])
        if commits:
            lines.append("Últimos commits:")
            for c in commits:
                lines.append(f"- `{c['sha']}` {c['message']} ({c['date'][:10]})")

    return {
        "ok": True,
        "summary": "\n".join(lines),
        "profile": profile,
        "repos": repos,
        "matched_repo": matched_repo_detail,
    }

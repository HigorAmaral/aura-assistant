import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx

from storage import get_settings, log_activity
from remote_bridge import push_mobile_notification

BASE_DIR = Path(__file__).parent.resolve()
VERSION_FILE = BASE_DIR / ".aura_version.json"

_UPDATE_STATE: Dict[str, Any] = {
    "daemon_started": False,
    "checking": False,
    "updating": False,
    "update_available": False,
    "local_sha": "",
    "remote_sha": "",
    "remote_message": "",
    "remote_date": "",
    "mode": "unknown",
    "last_checked_at": None,
    "last_updated_at": None,
    "last_error": None,
}
_LOCK = threading.Lock()


def _parse_owner_repo(repo_value: str) -> Tuple[str, str]:
    raw = (repo_value or "HigorAmaral/aura-assistant").strip()
    raw = raw.removesuffix(".git")
    if "github.com/" in raw:
        raw = raw.split("github.com/", 1)[1]
    parts = [p for p in raw.strip("/").split("/") if p]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "HigorAmaral", "aura-assistant"


def _has_git_repo() -> bool:
    return (BASE_DIR / ".git").exists() and shutil.which("git") is not None


def _run_git(*args: str, timeout: int = 20) -> subprocess.CompletedProcess:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.run(
        ["git", *args],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=flags,
    )


def get_local_version_info() -> Dict[str, Any]:
    if _has_git_repo():
        sha_res = _run_git("rev-parse", "HEAD")
        log_res = _run_git("log", "-1", "--format=%s|%ci")
        sha = sha_res.stdout.strip() if sha_res.returncode == 0 else ""
        msg, date = "", ""
        if log_res.returncode == 0 and "|" in log_res.stdout:
            msg, date = log_res.stdout.strip().split("|", 1)
        return {
            "mode": "git",
            "sha": sha,
            "short_sha": sha[:7] if sha else "local",
            "message": msg,
            "date": date,
        }

    if VERSION_FILE.exists():
        try:
            data = json.loads(VERSION_FILE.read_text(encoding="utf-8"))
            sha = str(data.get("sha", ""))
            return {
                "mode": "github_zip",
                "sha": sha,
                "short_sha": sha[:7] if sha else "portable",
                "message": data.get("message", ""),
                "date": data.get("updated_at", ""),
            }
        except Exception:
            pass

    return {
        "mode": "github_zip",
        "sha": "",
        "short_sha": "portable",
        "message": "Versão local sem histórico Git",
        "date": "",
    }


def check_for_updates() -> Dict[str, Any]:
    settings = get_settings()
    repo_str = str(settings.get("update_repo") or "HigorAmaral/aura-assistant")
    branch = str(settings.get("update_branch") or "main").strip() or "main"
    owner, repo = _parse_owner_repo(repo_str)

    with _LOCK:
        _UPDATE_STATE["checking"] = True
        _UPDATE_STATE["last_error"] = None

    try:
        local_info = get_local_version_info()
        local_sha = local_info["sha"]
        mode = local_info["mode"]

        if mode == "git":
            remotes = _run_git("remote")
            if "origin" not in remotes.stdout.split():
                _run_git("remote", "add", "origin", f"https://github.com/{owner}/{repo}.git")

            fetch = _run_git("fetch", "origin", branch, "--quiet", timeout=30)
            if fetch.returncode != 0:
                err = fetch.stderr.strip() or "Falha ao executar git fetch."
                raise RuntimeError(err)

            rem = _run_git("rev-parse", f"origin/{branch}")
            if rem.returncode != 0:
                raise RuntimeError(rem.stderr.strip() or f"Branch origin/{branch} não encontrada.")

            remote_sha = rem.stdout.strip()
            rem_log = _run_git("log", "-1", f"origin/{branch}", "--format=%s|%ci")
            remote_msg, remote_date = "", ""
            if rem_log.returncode == 0 and "|" in rem_log.stdout:
                remote_msg, remote_date = rem_log.stdout.strip().split("|", 1)
        else:
            api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(api_url, headers={"Accept": "application/vnd.github+json", "User-Agent": "AURA-OS-Updater"})
                if resp.status_code != 200:
                    raise RuntimeError(f"GitHub API HTTP {resp.status_code}: {resp.text[:160]}")
                data = resp.json()
                remote_sha = str(data.get("sha", ""))
                commit_obj = data.get("commit", {})
                remote_msg = str(commit_obj.get("message", "")).splitlines()[0] if commit_obj.get("message") else ""
                remote_date = str((commit_obj.get("committer") or {}).get("date", ""))

        update_available = bool(remote_sha and remote_sha != local_sha)
        now_iso = datetime.now().isoformat(timespec="seconds")

        with _LOCK:
            _UPDATE_STATE.update({
                "checking": False,
                "update_available": update_available,
                "local_sha": local_sha,
                "remote_sha": remote_sha,
                "remote_message": remote_msg,
                "remote_date": remote_date,
                "mode": mode,
                "last_checked_at": now_iso,
                "last_error": None,
            })

        return {
            "ok": True,
            "repo": f"{owner}/{repo}",
            "branch": branch,
            "mode": mode,
            "update_available": update_available,
            "local_sha": local_sha,
            "local_short": local_sha[:7] if local_sha else "local",
            "remote_sha": remote_sha,
            "remote_short": remote_sha[:7] if remote_sha else "",
            "remote_message": remote_msg,
            "remote_date": remote_date,
            "last_checked_at": now_iso,
        }
    except Exception as exc:
        now_iso = datetime.now().isoformat(timespec="seconds")
        with _LOCK:
            _UPDATE_STATE["checking"] = False
            _UPDATE_STATE["last_checked_at"] = now_iso
            _UPDATE_STATE["last_error"] = str(exc)
        return {
            "ok": False,
            "repo": f"{owner}/{repo}",
            "branch": branch,
            "error": str(exc),
            "last_checked_at": now_iso,
        }


def _install_requirements_if_needed() -> None:
    req_file = BASE_DIR / "requirements.txt"
    if not req_file.exists():
        return
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file), "--quiet"],
            cwd=str(BASE_DIR),
            timeout=180,
            capture_output=True,
            creationflags=flags,
        )
    except Exception:
        pass


def _schedule_self_restart(delay_sec: float = 1.2) -> None:
    def _restart():
        time.sleep(delay_sec)
        entry_script = BASE_DIR / "desktop_widget.py"
        if not entry_script.exists():
            entry_script = BASE_DIR / "app.py"
        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(
                [sys.executable, str(entry_script)],
                cwd=str(BASE_DIR),
                creationflags=creationflags,
                close_fds=True,
            )
        finally:
            os._exit(0)

    threading.Thread(target=_restart, daemon=True).start()


def apply_update(restart: bool = True) -> Dict[str, Any]:
    check = check_for_updates()
    if not check.get("ok"):
        return {"success": False, "message": f"Erro ao verificar atualização: {check.get('error')}"}

    if not check.get("update_available"):
        return {
            "success": True,
            "updated": False,
            "message": f"AURA OS já está atualizada na branch `{check['branch']}` ({check['local_short']}).",
            "check": check,
        }

    settings = get_settings()
    owner, repo = _parse_owner_repo(str(settings.get("update_repo") or "HigorAmaral/aura-assistant"))
    branch = check["branch"]
    remote_sha = check["remote_sha"]
    remote_short = check["remote_short"]
    remote_msg = check.get("remote_message", "")

    with _LOCK:
        _UPDATE_STATE["updating"] = True
        _UPDATE_STATE["last_error"] = None

    try:
        req_changed = False
        if check["mode"] == "git":
            diff_res = _run_git("diff", "--name-only", "HEAD", f"origin/{branch}")
            changed_files = diff_res.stdout.splitlines() if diff_res.returncode == 0 else []
            req_changed = "requirements.txt" in changed_files

            reset_res = _run_git("reset", "--hard", f"origin/{branch}", timeout=30)
            if reset_res.returncode != 0:
                raise RuntimeError(reset_res.stderr.strip() or "Falha ao aplicar git reset --hard.")
        else:
            zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
            with httpx.Client(timeout=45.0, follow_redirects=True) as client:
                resp = client.get(zip_url, headers={"User-Agent": "AURA-OS-Updater"})
                if resp.status_code != 200:
                    raise RuntimeError(f"Falha ao baixar pacote da branch {branch}: HTTP {resp.status_code}")
                zip_bytes = resp.content

            old_req = (BASE_DIR / "requirements.txt").read_text(encoding="utf-8") if (BASE_DIR / "requirements.txt").exists() else ""
            skip_names = {"aura_data.db", ".env", "update_state.json", ".aura_version.json"}

            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                    zf.extractall(tmp_path)

                extracted_roots = [p for p in tmp_path.iterdir() if p.is_dir()]
                if not extracted_roots:
                    raise RuntimeError("Arquivo ZIP do repositório veio vazio.")
                src_root = extracted_roots[0]

                for item in src_root.rglob("*"):
                    rel = item.relative_to(src_root)
                    if any(part in ("__pycache__", ".git", "dist", "build") for part in rel.parts):
                        continue
                    if rel.name in skip_names or rel.name.startswith("aura_data.db"):
                        continue
                    dest = BASE_DIR / rel
                    if item.is_dir():
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dest)

            new_req = (BASE_DIR / "requirements.txt").read_text(encoding="utf-8") if (BASE_DIR / "requirements.txt").exists() else ""
            req_changed = old_req != new_req

        VERSION_FILE.write_text(
            json.dumps(
                {
                    "sha": remote_sha,
                    "message": remote_msg,
                    "branch": branch,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        if req_changed:
            _install_requirements_if_needed()

        now_iso = datetime.now().isoformat(timespec="seconds")
        with _LOCK:
            _UPDATE_STATE.update({
                "updating": False,
                "update_available": False,
                "local_sha": remote_sha,
                "last_updated_at": now_iso,
                "last_error": None,
            })

        summary_msg = f"AURA OS atualizada automaticamente via branch `{branch}` para `{remote_short}`: {remote_msg}"
        log_activity("UPDATE", summary_msg)
        try:
            push_mobile_notification("Atualização Concluída (main)", summary_msg, "success")
        except Exception:
            pass

        if restart:
            _schedule_self_restart(1.2)

        return {
            "success": True,
            "updated": True,
            "restarting": restart,
            "sha": remote_sha,
            "short_sha": remote_short,
            "message": summary_msg,
        }
    except Exception as exc:
        with _LOCK:
            _UPDATE_STATE["updating"] = False
            _UPDATE_STATE["last_error"] = str(exc)
        return {"success": False, "message": f"Erro ao atualizar AURA OS: {exc}"}


def get_update_status() -> Dict[str, Any]:
    settings = get_settings()
    local_info = get_local_version_info()
    with _LOCK:
        state = dict(_UPDATE_STATE)
    return {
        "repo": settings.get("update_repo", "HigorAmaral/aura-assistant"),
        "branch": settings.get("update_branch", "main"),
        "auto_update_enabled": bool(settings.get("auto_update_enabled", True)),
        "auto_restart_on_update": bool(settings.get("auto_restart_on_update", True)),
        "check_interval_sec": int(settings.get("update_check_interval_sec", 60) or 60),
        "local": local_info,
        "state": state,
    }


def start_auto_update_daemon() -> None:
    with _LOCK:
        if _UPDATE_STATE["daemon_started"]:
            return
        _UPDATE_STATE["daemon_started"] = True

    def _loop():
        time.sleep(8)
        while True:
            try:
                settings = get_settings()
                interval = max(20, int(settings.get("update_check_interval_sec", 60) or 60))
                if settings.get("auto_update_enabled", True):
                    res = check_for_updates()
                    if res.get("ok") and res.get("update_available"):
                        apply_update(restart=bool(settings.get("auto_restart_on_update", True)))
                time.sleep(interval)
            except Exception:
                time.sleep(60)

    threading.Thread(target=_loop, daemon=True, name="aura-auto-updater").start()


def build_portable_app_zip() -> bytes:
    """Create a clean downloadable ZIP of the AURA OS app (excluding local DB, caches, and .git)."""
    local_info = get_local_version_info()
    buf = io.BytesIO()
    excluded_dirs = {"__pycache__", ".git", "build", "dist", "release", ".venv", "venv"}
    excluded_files = {"aura_data.db", ".env", "update_state.json"}

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in BASE_DIR.rglob("*"):
            rel = item.relative_to(BASE_DIR)
            if any(part in excluded_dirs for part in rel.parts):
                continue
            if item.is_dir():
                continue
            if rel.name in excluded_files or rel.name.startswith("aura_data.db") or rel.suffix in {".pyc", ".log", ".spec"}:
                continue
            zf.write(item, arcname=f"aura-assistant/{rel.as_posix()}")

        version_payload = json.dumps(
            {
                "sha": local_info.get("sha", ""),
                "message": local_info.get("message", ""),
                "packaged_at": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        )
        zf.writestr("aura-assistant/.aura_version.json", version_payload)

    buf.seek(0)
    return buf.read()

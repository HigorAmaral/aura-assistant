import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

IS_WINDOWS = platform.system().lower() == "windows"
IS_LINUX = platform.system().lower() == "linux"
IS_MAC = platform.system().lower() == "darwin"

_BACKEND_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}


def windows_to_wsl_path(win_path: str) -> str:
    """Convert a Windows path like C:\\Users\\Name to /mnt/c/Users/Name."""
    p = str(win_path).replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/(.*)$", p)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2)
        return f"/mnt/{drive}/{rest}".rstrip("/") or f"/mnt/{drive}"
    return p


def _find_git_bash() -> Optional[str]:
    if not IS_WINDOWS:
        return shutil.which("bash")
    candidates = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        str(Path.home() / r"AppData\Local\Programs\Git\bin\bash.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    which_bash = shutil.which("bash")
    if which_bash and "system32" not in which_bash.lower():
        return which_bash
    return None


def _detect_wsl_distro() -> Optional[str]:
    if not IS_WINDOWS:
        return None
    wsl_exe = shutil.which("wsl") or shutil.which("wsl.exe")
    if not wsl_exe:
        return None
    try:
        proc = subprocess.run(
            [wsl_exe, "-l", "-q"],
            capture_output=True,
            timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if proc.returncode != 0:
            return None
        raw = proc.stdout or b""
        # wsl.exe outputs UTF-16LE on Windows
        text = raw.decode("utf-16-le", errors="ignore") if b"\x00" in raw else raw.decode("utf-8", errors="ignore")
        distros = [line.strip().lstrip("\ufeff") for line in text.splitlines() if line.strip()]
        # Filter out docker-desktop helper distros and error lines
        usable = [d for d in distros if "docker-desktop" not in d.lower() and " " not in d]
        for d in usable:
            if "ubuntu" in d.lower():
                return d
        return usable[0] if usable else None
    except Exception:
        return None


def _has_docker_daemon() -> bool:
    docker_exe = shutil.which("docker")
    if not docker_exe:
        return False
    try:
        kwargs: Dict[str, Any] = {"capture_output": True, "timeout": 2}
        if IS_WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.run([docker_exe, "info", "--format", "{{.ServerVersion}}"], **kwargs)
        return proc.returncode == 0
    except Exception:
        return False


def detect_ubuntu_backend(force_refresh: bool = False) -> Dict[str, Any]:
    """Detect the best available Ubuntu/Linux execution backend on the current OS."""
    now = time.monotonic()
    if not force_refresh and _BACKEND_CACHE["data"] is not None and (now - _BACKEND_CACHE["ts"]) < 30.0:
        return dict(_BACKEND_CACHE["data"])

    available: List[str] = ["python_posix"]
    wsl_distro = _detect_wsl_distro()
    docker_ok = _has_docker_daemon()
    git_bash = _find_git_bash()

    if IS_LINUX:
        available.insert(0, "native_bash")
    if wsl_distro:
        available.insert(0, "wsl")
    if docker_ok:
        available.append("docker")
    if git_bash and IS_WINDOWS:
        available.append("git_bash")

    if IS_LINUX:
        primary = "native_bash"
        label = f"Ubuntu/Linux Bash ({platform.release()})"
    elif wsl_distro:
        primary = "wsl"
        label = f"WSL ({wsl_distro})"
    elif docker_ok:
        primary = "docker"
        label = "Docker (ubuntu:latest)"
    elif git_bash:
        primary = "git_bash"
        label = "Git Bash (POSIX)"
    else:
        primary = "python_posix"
        label = "Ubuntu Shell Universal (Python)"

    info = {
        "ok": True,
        "os": platform.system(),
        "primary_backend": primary,
        "label": label,
        "wsl_distro": wsl_distro or "",
        "docker_available": docker_ok,
        "git_bash_path": git_bash or "",
        "available_backends": available,
    }
    _BACKEND_CACHE["data"] = dict(info)
    _BACKEND_CACHE["ts"] = now
    return info


def _resolve_path(cwd: str, target: str) -> Path:
    if target in ("~", ""):
        return Path.home()
    if target.startswith("~/"):
        return (Path.home() / target[2:]).resolve()
    p = Path(target)
    if p.is_absolute():
        return p.resolve()
    return (Path(cwd) / p).resolve()


def _run_python_posix_single(cmd_str: str, cwd: str, env: Dict[str, str], stdin_text: str = "") -> Dict[str, Any]:
    """Execute a single POSIX/Ubuntu-style command purely in Python (100% cross-platform)."""
    try:
        tokens = shlex.split(cmd_str, posix=True)
    except ValueError as exc:
        return {"output": f"bash: erro de sintaxe: {exc}", "exit_code": 2, "cwd": cwd}

    if not tokens:
        return {"output": "", "exit_code": 0, "cwd": cwd}

    cmd = tokens[0]
    args = tokens[1:]
    flags = {a for a in args if a.startswith("-")}
    pos_args = [a for a in args if not a.startswith("-")]

    if cmd == "pwd":
        return {"output": windows_to_wsl_path(cwd) if IS_WINDOWS else cwd, "exit_code": 0, "cwd": cwd}

    if cmd == "echo":
        return {"output": " ".join(args), "exit_code": 0, "cwd": cwd}

    if cmd == "whoami":
        return {"output": os.environ.get("USERNAME") or os.environ.get("USER") or "aura", "exit_code": 0, "cwd": cwd}

    if cmd == "hostname":
        return {"output": socket.gethostname(), "exit_code": 0, "cwd": cwd}

    if cmd == "date":
        return {"output": datetime.now().strftime("%a %b %d %H:%M:%S %Z %Y"), "exit_code": 0, "cwd": cwd}

    if cmd == "uname":
        if "-a" in flags:
            return {
                "output": f"Linux {socket.gethostname()} 6.8.0-aura-generic #1 SMP {platform.machine()} GNU/Linux (Host: {platform.system()})",
                "exit_code": 0,
                "cwd": cwd,
            }
        return {"output": "Linux", "exit_code": 0, "cwd": cwd}

    if cmd == "help":
        return {
            "output": (
                "Ubuntu Shell Universal (AURA OS) — Comandos integrados:\n"
                "  Navegação & Arquivos : ls [-la], cd, pwd, cat, head, tail, mkdir [-p], touch, rm [-rf], cp [-r], mv, find, grep [-in], wc [-l]\n"
                "  Sistema & Hardware   : uname [-a], whoami, hostname, date, df [-h], free [-h], ps [aux], env, which\n"
                "  Ferramentas Host     : python, python3, pip, git, node, npm, curl (executados automaticamente se instalados)"
            ),
            "exit_code": 0,
            "cwd": cwd,
        }

    if cmd == "ls":
        show_all = any("a" in f for f in flags)
        long_fmt = any("l" in f for f in flags)
        target = _resolve_path(cwd, pos_args[0]) if pos_args else Path(cwd)
        if not target.exists():
            return {"output": f"ls: cannot access '{pos_args[0]}': No such file or directory", "exit_code": 2, "cwd": cwd}
        if target.is_file():
            return {"output": target.name, "exit_code": 0, "cwd": cwd}
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        lines = []
        for e in entries:
            if not show_all and e.name.startswith("."):
                continue
            if long_fmt:
                try:
                    st = e.stat()
                    kind = "d" if e.is_dir() else "-"
                    mtime = datetime.fromtimestamp(st.st_mtime).strftime("%b %d %H:%M")
                    size = f"{st.st_size:>8}"
                    suffix = "/" if e.is_dir() else ""
                    lines.append(f"{kind}rwxr-xr-x 1 aura aura {size} {mtime} {e.name}{suffix}")
                except OSError:
                    lines.append(f"?--------- ? ? ? ? {e.name}")
            else:
                lines.append(f"{e.name}/" if e.is_dir() else e.name)
        return {"output": "\n".join(lines) if long_fmt else "  ".join(lines), "exit_code": 0, "cwd": cwd}

    if cmd == "cat":
        if not pos_args:
            return {"output": stdin_text, "exit_code": 0, "cwd": cwd}
        outs = []
        for fn in pos_args:
            fp = _resolve_path(cwd, fn)
            if not fp.is_file():
                return {"output": f"cat: {fn}: No such file or directory", "exit_code": 1, "cwd": cwd}
            outs.append(fp.read_text(encoding="utf-8", errors="replace"))
        return {"output": "\n".join(outs), "exit_code": 0, "cwd": cwd}

    if cmd in ("head", "tail"):
        n_lines = 10
        for f in flags:
            if f.startswith("-n") and len(f) > 2 and f[2:].isdigit():
                n_lines = int(f[2:])
            elif f[1:].isdigit():
                n_lines = int(f[1:])
        text_data = stdin_text
        if pos_args:
            fp = _resolve_path(cwd, pos_args[0])
            if not fp.is_file():
                return {"output": f"{cmd}: {pos_args[0]}: No such file or directory", "exit_code": 1, "cwd": cwd}
            text_data = fp.read_text(encoding="utf-8", errors="replace")
        all_lines = text_data.splitlines()
        selected = all_lines[:n_lines] if cmd == "head" else all_lines[-n_lines:]
        return {"output": "\n".join(selected), "exit_code": 0, "cwd": cwd}

    if cmd == "wc":
        text_data = stdin_text
        if pos_args:
            fp = _resolve_path(cwd, pos_args[0])
            if not fp.is_file():
                return {"output": f"wc: {pos_args[0]}: No such file or directory", "exit_code": 1, "cwd": cwd}
            text_data = fp.read_text(encoding="utf-8", errors="replace")
        lines_c = len(text_data.splitlines())
        words_c = len(text_data.split())
        bytes_c = len(text_data.encode("utf-8"))
        if "-l" in flags:
            return {"output": str(lines_c), "exit_code": 0, "cwd": cwd}
        return {"output": f"  {lines_c}  {words_c}  {bytes_c}", "exit_code": 0, "cwd": cwd}

    if cmd == "grep":
        if not pos_args:
            return {"output": "Usage: grep [OPTION]... PATTERN [FILE]...", "exit_code": 2, "cwd": cwd}
        pattern = pos_args[0]
        ignore_case = any("i" in f for f in flags)
        line_nums = any("n" in f for f in flags)
        re_flags = re.IGNORECASE if ignore_case else 0
        try:
            rx = re.compile(pattern, re_flags)
        except re.error as exc:
            return {"output": f"grep: regex inválido: {exc}", "exit_code": 2, "cwd": cwd}

        matches = []
        if len(pos_args) == 1:
            for idx, line in enumerate(stdin_text.splitlines(), 1):
                if rx.search(line):
                    matches.append(f"{idx}:{line}" if line_nums else line)
        else:
            for fn in pos_args[1:]:
                fp = _resolve_path(cwd, fn)
                if fp.is_file():
                    for idx, line in enumerate(fp.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                        if rx.search(line):
                            prefix = f"{fn}:" if len(pos_args) > 2 else ""
                            num = f"{idx}:" if line_nums else ""
                            matches.append(f"{prefix}{num}{line}")
        return {"output": "\n".join(matches), "exit_code": 0 if matches else 1, "cwd": cwd}

    if cmd == "mkdir":
        if not pos_args:
            return {"output": "mkdir: missing operand", "exit_code": 1, "cwd": cwd}
        parents = any("p" in f for f in flags)
        for d in pos_args:
            _resolve_path(cwd, d).mkdir(parents=parents, exist_ok=parents)
        return {"output": "", "exit_code": 0, "cwd": cwd}

    if cmd == "touch":
        if not pos_args:
            return {"output": "touch: missing file operand", "exit_code": 1, "cwd": cwd}
        for fn in pos_args:
            fp = _resolve_path(cwd, fn)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.touch()
        return {"output": "", "exit_code": 0, "cwd": cwd}

    if cmd == "rm":
        if not pos_args:
            return {"output": "rm: missing operand", "exit_code": 1, "cwd": cwd}
        recursive = any("r" in f or "R" in f for f in flags)
        force = any("f" in f for f in flags)
        for fn in pos_args:
            fp = _resolve_path(cwd, fn)
            if not fp.exists():
                if not force:
                    return {"output": f"rm: cannot remove '{fn}': No such file or directory", "exit_code": 1, "cwd": cwd}
                continue
            if fp.is_dir():
                if not recursive:
                    return {"output": f"rm: cannot remove '{fn}': Is a directory", "exit_code": 1, "cwd": cwd}
                shutil.rmtree(fp)
            else:
                fp.unlink()
        return {"output": "", "exit_code": 0, "cwd": cwd}

    if cmd in ("cp", "mv") and len(pos_args) >= 2:
        src = _resolve_path(cwd, pos_args[0])
        dst = _resolve_path(cwd, pos_args[1])
        if not src.exists():
            return {"output": f"{cmd}: cannot stat '{pos_args[0]}': No such file or directory", "exit_code": 1, "cwd": cwd}
        if cmd == "mv":
            shutil.move(str(src), str(dst))
        else:
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        return {"output": "", "exit_code": 0, "cwd": cwd}

    if cmd == "find":
        root = _resolve_path(cwd, pos_args[0]) if pos_args else Path(cwd)
        name_pat = None
        if "-name" in args:
            idx = args.index("-name")
            if idx + 1 < len(args):
                name_pat = args[idx + 1]
        found = []
        for p in root.rglob(name_pat or "*"):
            found.append(str(p.relative_to(root)))
            if len(found) >= 100:
                break
        return {"output": "\n".join(found), "exit_code": 0, "cwd": cwd}

    if cmd == "df":
        lines = ["Filesystem      Size  Used Avail Use% Mounted on"]
        for part in psutil.disk_partitions(all=False):
            try:
                du = psutil.disk_usage(part.mountpoint)
                lines.append(
                    f"{part.device:<15} {du.total // (1024**3):>3}G  {du.used // (1024**3):>3}G  {du.free // (1024**3):>4}G  {int(du.percent):>2}% {part.mountpoint}"
                )
            except Exception:
                continue
        return {"output": "\n".join(lines), "exit_code": 0, "cwd": cwd}

    if cmd == "free":
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        div = (1024**3) if "-h" in flags else (1024**2)
        unit = "Gi" if "-h" in flags else "Mi"
        out = (
            f"               total        used        free      available\n"
            f"Mem:      {vm.total/div:>8.1f}{unit} {vm.used/div:>8.1f}{unit} {vm.free/div:>8.1f}{unit} {vm.available/div:>8.1f}{unit}\n"
            f"Swap:     {sw.total/div:>8.1f}{unit} {sw.used/div:>8.1f}{unit} {sw.free/div:>8.1f}{unit}"
        )
        return {"output": out, "exit_code": 0, "cwd": cwd}

    if cmd == "ps":
        lines = ["USER       PID  %CPU %MEM COMMAND"]
        for p in sorted(psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]), key=lambda x: x.info.get("memory_percent") or 0, reverse=True)[:20]:
            info = p.info
            lines.append(f"aura    {info['pid']:>6}  {(info.get('cpu_percent') or 0):>4.1f} {(info.get('memory_percent') or 0):>4.1f} {info.get('name')}")
        return {"output": "\n".join(lines), "exit_code": 0, "cwd": cwd}

    if cmd == "env":
        return {"output": "\n".join(f"{k}={v}" for k, v in sorted(env.items())[:40]), "exit_code": 0, "cwd": cwd}

    if cmd == "which" and pos_args:
        found = shutil.which(pos_args[0])
        return {"output": found or f"{pos_args[0]} not found", "exit_code": 0 if found else 1, "cwd": cwd}

    # Passthrough for common cross-platform CLI tools installed on the host
    host_cmd = "python" if cmd == "python3" and not shutil.which("python3") else cmd
    exe = shutil.which(host_cmd)
    if exe:
        try:
            kwargs: Dict[str, Any] = {
                "cwd": cwd,
                "env": env,
                "input": stdin_text or None,
                "capture_output": True,
                "text": True,
                "timeout": 25,
            }
            if IS_WINDOWS:
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            proc = subprocess.run([exe] + args, **kwargs)
            out = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
            return {"output": out, "exit_code": proc.returncode, "cwd": cwd}
        except Exception as exc:
            return {"output": f"bash: {cmd}: {exc}", "exit_code": 1, "cwd": cwd}

    return {"output": f"bash: {cmd}: command not found (digite 'help' para ver comandos disponíveis)", "exit_code": 127, "cwd": cwd}


def _execute_python_posix(command: str, cwd: str, env: Dict[str, str]) -> Dict[str, Any]:
    """Support simple pipelines like `ls -la | grep py` on top of the Python POSIX shell."""
    parts = [p.strip() for p in command.split("|") if p.strip()]
    stdin_buf = ""
    last_res = {"output": "", "exit_code": 0, "cwd": cwd}
    for part in parts:
        last_res = _run_python_posix_single(part, cwd, env, stdin_text=stdin_buf)
        stdin_buf = last_res.get("output", "")
    return last_res


def _decode_bytes(raw: Optional[bytes]) -> str:
    if not raw:
        return ""
    if b"\x00" in raw:
        return raw.decode("utf-16-le", errors="replace").lstrip("\ufeff")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def execute_ubuntu_command(
    command: str,
    cwd: str,
    env: Optional[Dict[str, str]] = None,
    timeout_sec: int = 30,
    preferred_backend: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a command in an integrated Ubuntu/Linux environment on any OS."""
    cmd_clean = (command or "").strip()
    proc_env = env if env is not None else os.environ.copy()

    # Handle `cd` consistently so session cwd stays in sync
    if cmd_clean == "cd" or cmd_clean.startswith("cd "):
        target = cmd_clean[2:].strip().strip('"').strip("'")
        new_path = _resolve_path(cwd, target)
        if new_path.exists() and new_path.is_dir():
            return {
                "output": f"Diretório ativo: {new_path}",
                "exit_code": 0,
                "cwd": str(new_path),
                "backend": "ubuntu_cd",
                "backend_label": "Ubuntu Shell",
            }
        return {
            "output": f"bash: cd: {target}: No such file or directory",
            "exit_code": 1,
            "cwd": cwd,
            "backend": "ubuntu_cd",
            "backend_label": "Ubuntu Shell",
        }

    info = detect_ubuntu_backend()
    backend = preferred_backend if preferred_backend in info["available_backends"] else info["primary_backend"]

    if backend == "native_bash":
        proc = subprocess.run(
            ["bash", "-lc", cmd_clean],
            cwd=cwd,
            env=proc_env,
            capture_output=True,
            timeout=timeout_sec,
        )
        out = (_decode_bytes(proc.stdout) + ("\n" + _decode_bytes(proc.stderr) if proc.stderr else "")).strip()
        return {"output": out, "exit_code": proc.returncode, "cwd": cwd, "backend": backend, "backend_label": info["label"]}

    if backend == "wsl":
        wsl_exe = shutil.which("wsl") or shutil.which("wsl.exe") or "wsl.exe"
        wsl_cwd = windows_to_wsl_path(cwd)
        distro = info.get("wsl_distro")
        cmd_args = [wsl_exe]
        if distro:
            cmd_args.extend(["-d", distro])
        cmd_args.extend(["--cd", cwd, "bash", "-lc", cmd_clean])
        proc = subprocess.run(
            cmd_args,
            env=proc_env,
            capture_output=True,
            timeout=timeout_sec,
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )
        out = (_decode_bytes(proc.stdout) + ("\n" + _decode_bytes(proc.stderr) if proc.stderr else "")).strip()
        return {"output": out or f"(WSL {wsl_cwd})", "exit_code": proc.returncode, "cwd": cwd, "backend": backend, "backend_label": info["label"]}

    if backend == "docker":
        docker_exe = shutil.which("docker") or "docker"
        kwargs: Dict[str, Any] = {"capture_output": True, "timeout": timeout_sec}
        if IS_WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.run(
            [docker_exe, "run", "--rm", "-v", f"{cwd}:/workspace", "-w", "/workspace", "ubuntu:latest", "bash", "-lc", cmd_clean],
            **kwargs,
        )
        out = (_decode_bytes(proc.stdout) + ("\n" + _decode_bytes(proc.stderr) if proc.stderr else "")).strip()
        return {"output": out, "exit_code": proc.returncode, "cwd": cwd, "backend": backend, "backend_label": "Docker (ubuntu:latest)"}

    if backend == "git_bash" and info.get("git_bash_path"):
        proc = subprocess.run(
            [info["git_bash_path"], "-lc", cmd_clean],
            cwd=cwd,
            env=proc_env,
            capture_output=True,
            timeout=timeout_sec,
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )
        out = (_decode_bytes(proc.stdout) + ("\n" + _decode_bytes(proc.stderr) if proc.stderr else "")).strip()
        return {"output": out, "exit_code": proc.returncode, "cwd": cwd, "backend": backend, "backend_label": "Git Bash (POSIX)"}

    # Fallback: Universal Python POSIX/Ubuntu Shell
    res = _execute_python_posix(cmd_clean, cwd, proc_env)
    return {**res, "backend": "python_posix", "backend_label": "Ubuntu Shell Universal (Python)"}

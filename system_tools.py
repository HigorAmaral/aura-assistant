import os
import sys
import time
import socket
import shutil
import platform
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import psutil
from storage import log_activity, save_synced_apps_batch, list_synced_apps, delete_synced_app

OS_NAME = platform.system()  # 'Windows', 'Linux', 'Darwin'
IS_WINDOWS = OS_NAME == "Windows"
IS_LINUX = OS_NAME == "Linux"

_last_net_io = psutil.net_io_counters()
_last_net_time = time.time()


def get_lan_ip() -> str:
    """Discover the primary local Wi-Fi / LAN IPv4 address for smartphone connectivity."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


# Cross-platform App Catalog with Vector Icon IDs (Zero Emojis)
KNOWN_APPS: Dict[str, Dict[str, Any]] = {
    "calculadora": {
        "name": "Calculadora",
        "win_cmd": "calc.exe",
        "linux_cmd": ["gnome-calculator", "galculator", "kcalc", "xcalc"],
        "icon": "calculator",
        "cat": "Utilitários",
    },
    "bloco de notas": {
        "name": "Editor de Texto",
        "win_cmd": "notepad.exe",
        "linux_cmd": ["gnome-text-editor", "gedit", "mousepad", "kate", "xed"],
        "icon": "file-text",
        "cat": "Produtividade",
    },
    "paint": {
        "name": "Desenho / Imagem",
        "win_cmd": "mspaint.exe",
        "linux_cmd": ["drawing", "kolourpaint", "gimp", "pinta"],
        "icon": "palette",
        "cat": "Criativo",
    },
    "explorador": {
        "name": "Gerenciador de Arquivos",
        "win_cmd": "explorer.exe",
        "linux_cmd": ["nautilus", "nemo", "dolphin", "thunar", "xdg-open"],
        "icon": "folder",
        "cat": "Sistema",
    },
    "terminal": {
        "name": "Terminal do Sistema",
        "win_cmd": "powershell.exe",
        "linux_cmd": ["gnome-terminal", "x-terminal-emulator", "konsole", "xfce4-terminal", "xterm"],
        "icon": "terminal",
        "cat": "Dev",
    },
    "configuracoes": {
        "name": "Configurações do SO",
        "win_cmd": "ms-settings:",
        "linux_cmd": ["gnome-control-center", "systemsettings5", "xfce4-settings-manager"],
        "icon": "settings",
        "cat": "Sistema",
    },
    "gerenciador de tarefas": {
        "name": "Monitor do Sistema",
        "win_cmd": "taskmgr.exe",
        "linux_cmd": ["gnome-system-monitor", "ksysguard", "xfce4-taskmanager", "htop"],
        "icon": "activity",
        "cat": "Sistema",
    },
    "recorte": {
        "name": "Ferramenta de Captura",
        "win_cmd": "snippingtool.exe",
        "linux_cmd": ["gnome-screenshot -i", "flameshot gui", "spectacle"],
        "icon": "camera",
        "cat": "Utilitários",
    },
    "navegador": {
        "name": "Navegador Padrão",
        "win_cmd": "https://www.google.com",
        "linux_cmd": ["xdg-open https://www.google.com"],
        "icon": "globe",
        "cat": "Web",
    },
    "chrome": {
        "name": "Google Chrome",
        "win_cmd": "chrome",
        "linux_cmd": ["google-chrome", "chromium-browser", "chromium"],
        "icon": "compass",
        "cat": "Web",
    },
    "vscode": {
        "name": "VS Code",
        "win_cmd": "code",
        "linux_cmd": ["code", "codium"],
        "icon": "code",
        "cat": "Dev",
    },
    "spotify": {
        "name": "Spotify",
        "win_cmd": "spotify:",
        "linux_cmd": ["spotify", "flatpak run com.spotify.Client"],
        "icon": "music",
        "cat": "Mídia",
    },
    "downloads": {
        "name": "Pasta Downloads",
        "win_cmd": str(Path.home() / "Downloads"),
        "linux_cmd": [f'xdg-open "{Path.home() / "Downloads"}"'],
        "icon": "download",
        "cat": "Pastas",
    },
    "documentos": {
        "name": "Pasta Documentos",
        "win_cmd": str(Path.home() / "Documents"),
        "linux_cmd": [f'xdg-open "{Path.home() / "Documents"}"'],
        "icon": "book-open",
        "cat": "Pastas",
    },
    "youtube": {
        "name": "YouTube",
        "win_cmd": "https://www.youtube.com",
        "linux_cmd": ["xdg-open https://www.youtube.com"],
        "icon": "video",
        "cat": "Web",
    },
    "github": {
        "name": "GitHub",
        "win_cmd": "https://github.com",
        "linux_cmd": ["xdg-open https://github.com"],
        "icon": "git-branch",
        "cat": "Dev",
    },
}


_STATS_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
try:
    psutil.cpu_percent(interval=None)
except Exception:
    pass


def get_system_stats() -> Dict[str, Any]:
    """Return real-time CPU, RAM, Disk, Battery, Network Speed, OS Platform, LAN IP, and Top Processes."""
    global _last_net_io, _last_net_time

    now_cache = time.time()
    if _STATS_CACHE["data"] is not None and (now_cache - _STATS_CACHE["ts"]) < 1.5:
        return _STATS_CACHE["data"]

    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_cores = psutil.cpu_count(logical=True)
    cpu_freq = psutil.cpu_freq()
    freq_ghz = round(cpu_freq.current / 1000.0, 2) if cpu_freq and cpu_freq.current else 0.0

    vm = psutil.virtual_memory()
    root_drive = os.environ.get("SystemDrive", "C:\\") if IS_WINDOWS else "/"
    disk = psutil.disk_usage(root_drive)

    now = time.time()
    cur_net = psutil.net_io_counters()
    elapsed = max(now - _last_net_time, 0.2)
    down_kbs = round((cur_net.bytes_recv - _last_net_io.bytes_recv) / 1024.0 / elapsed, 1)
    up_kbs = round((cur_net.bytes_sent - _last_net_io.bytes_sent) / 1024.0 / elapsed, 1)
    _last_net_io = cur_net
    _last_net_time = now

    boot_ts = psutil.boot_time()
    uptime_secs = int(now - boot_ts)
    uptime_str = f"{uptime_secs // 3600}h {(uptime_secs % 3600) // 60}m"

    hostname = socket.gethostname()
    lan_ip = get_lan_ip()

    battery_info = None
    if hasattr(psutil, "sensors_battery"):
        try:
            bat = psutil.sensors_battery()
            if bat is not None:
                battery_info = {
                    "percent": round(bat.percent, 1),
                    "power_plugged": bool(bat.power_plugged),
                }
        except Exception:
            battery_info = None

    processes: List[Dict[str, Any]] = []
    ignored_procs = {"system idle process", "system", "registry", "memcompression", "kthreadd", "systemd"}
    for proc in psutil.process_iter(["pid", "name", "memory_percent", "cpu_percent"]):
        try:
            pinfo = proc.info
            if pinfo["name"] and pinfo["name"].lower() not in ignored_procs:
                processes.append(
                    {
                        "pid": pinfo["pid"],
                        "name": pinfo["name"],
                        "memory_percent": round(pinfo["memory_percent"] or 0.0, 1),
                        "cpu_percent": round(pinfo["cpu_percent"] or 0.0, 1),
                    }
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    processes.sort(key=lambda x: x["memory_percent"], reverse=True)

    os_label = f"Windows {platform.release()}" if IS_WINDOWS else f"Linux ({platform.system()} {platform.release()})"

    result = {
        "os": {
            "platform": OS_NAME,
            "label": os_label,
            "is_windows": IS_WINDOWS,
            "is_linux": IS_LINUX,
        },
        "cpu": {
            "percent": round(cpu_percent, 1),
            "cores": cpu_cores,
            "freq_ghz": freq_ghz,
        },
        "ram": {
            "percent": round(vm.percent, 1),
            "used_gb": round(vm.used / (1024**3), 2),
            "total_gb": round(vm.total / (1024**3), 2),
            "available_gb": round(vm.available / (1024**3), 2),
        },
        "disk": {
            "percent": round(disk.percent, 1),
            "used_gb": round(disk.used / (1024**3), 1),
            "total_gb": round(disk.total / (1024**3), 1),
            "free_gb": round(disk.free / (1024**3), 1),
            "mount": root_drive,
        },
        "network": {
            "down_kbs": max(down_kbs, 0.0),
            "up_kbs": max(up_kbs, 0.0),
            "hostname": hostname,
            "local_ip": lan_ip,
            "mobile_url": f"http://{lan_ip}:8765/mobile",
            "uptime": uptime_str,
        },
        "battery": battery_info,
        "top_processes": processes[:8],
    }
    _STATS_CACHE["ts"] = time.time()
    _STATS_CACHE["data"] = result
    return result


def find_start_menu_or_desktop_entry(app_query: str) -> Optional[str]:
    """Search Windows Start Menu (.lnk) or Linux Ubuntu (.desktop) applications."""
    q = app_query.lower().strip()
    if IS_WINDOWS:
        start_dirs = [
            Path(os.environ.get("ProgramData", "C:\\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        ]
        for base in start_dirs:
            if not base.exists():
                continue
            try:
                for item in base.rglob("*.lnk"):
                    if q in item.stem.lower():
                        return str(item)
            except Exception:
                continue
    else:
        desktop_dirs = [
            Path("/usr/share/applications"),
            Path("/var/lib/snapd/desktop/applications"),
            Path.home() / ".local" / "share" / "applications",
        ]
        for base in desktop_dirs:
            if not base.exists():
                continue
            try:
                for item in base.glob("*.desktop"):
                    if q in item.stem.lower():
                        return f"gtk-launch {item.stem}"
            except Exception:
                continue
    return None


def _win_launch_with_elevation_fallback(target: str) -> None:
    """Launch a Windows app/path, automatically using ShellExecute ('open' then 'runas') on WinError 740."""
    try:
        if shutil.which(target) and not target.lower().endswith((".lnk", ".url")):
            flags = subprocess.CREATE_NEW_CONSOLE if target.lower() in ("powershell.exe", "cmd.exe", "wt.exe") else 0
            subprocess.Popen([target], creationflags=flags)
        else:
            os.startfile(target)
    except OSError as e:
        if getattr(e, "winerror", None) == 740:
            import ctypes
            resolved = shutil.which(target) or target
            rc = ctypes.windll.shell32.ShellExecuteW(None, "open", resolved, None, None, 1)
            if rc <= 32:
                rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", resolved, None, None, 1)
            if rc <= 32:
                raise RuntimeError(f"Elevação recusada ou falhou (código {rc}).")
        else:
            raise


def open_application(app_name: str) -> Dict[str, Any]:
    """Cross-platform launcher for Windows and Linux Ubuntu."""
    clean = app_name.lower().strip()

    if clean.startswith(("http://", "https://", "www.")):
        url = clean if clean.startswith("http") else f"https://{clean}"
        webbrowser.open(url)
        log_activity("APP", f"Site aberto: {url}")
        return {"success": True, "app": url, "message": f"Site **{url}** aberto no navegador."}

    matched_entry = None
    for key, info in KNOWN_APPS.items():
        if clean == key or key in clean:
            matched_entry = info
            break

    # Also check user's synchronized installed apps from SQLite
    synced_match = None
    if not matched_entry:
        for sapp in list_synced_apps():
            if clean == sapp["id"] or clean == sapp["name"].lower() or clean in sapp["name"].lower():
                synced_match = sapp
                break

    if synced_match:
        display_name = synced_match["name"]
        target_path = synced_match["target_path"]
        try:
            if IS_WINDOWS:
                _win_launch_with_elevation_fallback(target_path)
            else:
                subprocess.Popen(target_path, shell=True)
            log_activity("APP SYNC", f"Iniciado app sincronizado: {display_name}")
            return {
                "success": True,
                "app": display_name,
                "message": f"Aplicativo sincronizado **{display_name}** iniciado com sucesso!",
            }
        except Exception as e:
            return {"success": False, "app": display_name, "message": f"Erro ao abrir '{display_name}': {e}"}

    display_name = matched_entry["name"] if matched_entry else app_name.strip()

    try:
        if IS_WINDOWS:
            target = matched_entry["win_cmd"] if matched_entry else clean
            # Smart resolution for common Dev/System apps on Windows
            if clean in ("vscode", "vs code", "code"):
                vs_candidates = [
                    shutil.which("code"),
                    str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe"),
                    str(Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Microsoft VS Code" / "Code.exe"),
                    find_start_menu_or_desktop_entry("visual studio code"),
                    find_start_menu_or_desktop_entry("cursor"),
                ]
                resolved_vs = next((c for c in vs_candidates if c and (os.path.exists(c) or shutil.which(c))), None)
                if resolved_vs:
                    target = resolved_vs

            if target.startswith(("http://", "https://")):
                webbrowser.open(target)
            elif target.endswith(":") or os.path.isdir(target) or os.path.isfile(target):
                _win_launch_with_elevation_fallback(target)
            else:
                shortcut = find_start_menu_or_desktop_entry(clean)
                if shortcut and os.path.exists(shortcut):
                    _win_launch_with_elevation_fallback(shortcut)
                elif shutil.which(target):
                    _win_launch_with_elevation_fallback(target)
                else:
                    try:
                        _win_launch_with_elevation_fallback(target)
                    except Exception as inner_e:
                        if getattr(inner_e, "winerror", None) == 740:
                            raise
                        subprocess.Popen(f'start "" "{target}"', shell=True)
        else:
            # Linux Ubuntu / POSIX execution
            if os.path.exists(app_name.strip()):
                subprocess.Popen(["xdg-open", app_name.strip()])
            elif matched_entry:
                candidates = matched_entry.get("linux_cmd", [])
                launched = False
                for cmd_str in candidates:
                    exe_name = cmd_str.split()[0]
                    if shutil.which(exe_name):
                        subprocess.Popen(cmd_str, shell=True)
                        launched = True
                        break
                if not launched:
                    subprocess.Popen(["xdg-open", clean])
            else:
                if shutil.which(clean):
                    subprocess.Popen([clean])
                else:
                    desktop_cmd = find_start_menu_or_desktop_entry(clean)
                    if desktop_cmd:
                        subprocess.Popen(desktop_cmd, shell=True)
                    else:
                        subprocess.Popen(["xdg-open", clean])

        log_activity("APP", f"Iniciado ({OS_NAME}): {display_name}")
        return {
            "success": True,
            "app": display_name,
            "message": f"Aplicativo **{display_name}** iniciado com sucesso no {OS_NAME}!",
        }
    except Exception as e:
        return {
            "success": False,
            "app": display_name,
            "message": f"Não foi possível abrir '{display_name}': {e}",
        }


def close_application(name_or_pid: str) -> Dict[str, Any]:
    protected = {
        "system",
        "registry",
        "smss.exe",
        "csrss.exe",
        "wininit.exe",
        "services.exe",
        "lsass.exe",
        "svchost.exe",
        "winlogon.exe",
        "dwm.exe",
        "explorer.exe",
        "python.exe",
        "pythonw.exe",
        "python3",
        "systemd",
        "gnome-shell",
        "xorg",
        "wayland",
    }
    target = str(name_or_pid).strip().lower()
    alias_map = {
        "calculadora": "calculatorapp.exe" if IS_WINDOWS else "gnome-calculator",
        "bloco de notas": "notepad.exe" if IS_WINDOWS else "gedit",
        "paint": "mspaint.exe" if IS_WINDOWS else "drawing",
        "chrome": "chrome.exe" if IS_WINDOWS else "chrome",
    }
    if target in alias_map:
        target = alias_map[target]

    killed: List[str] = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pname = (proc.info["name"] or "").lower()
            pid_str = str(proc.info["pid"])
            if pname in protected:
                continue
            if target == pid_str or (target and target in pname):
                proc.terminate()
                killed.append(f"{proc.info['name']} (PID {pid_str})")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if killed:
        summary = ", ".join(killed[:4])
        log_activity("APP", f"Encerrado: {summary}")
        return {
            "success": True,
            "closed": killed,
            "message": f"Encerrei {len(killed)} processo(s): **{summary}**",
        }
    return {
        "success": False,
        "closed": [],
        "message": f"Nenhum processo ativo encontrado correspondente a '{name_or_pid}'.",
    }


def _classify_app_metadata(name: str) -> tuple[str, str]:
    n = name.lower()
    if any(k in n for k in ("code", "visual studio", "cursor", "git", "python", "node", "docker", "postman", "terminal", "powershell", "bash", "intellij", "pycharm", "android", "heidisql", "dbeaver")):
        return ("Dev", "code-2")
    if any(k in n for k in ("chrome", "edge", "firefox", "brave", "opera", "navegador", "browser")):
        return ("Web", "globe")
    if any(k in n for k in ("discord", "whatsapp", "telegram", "slack", "teams", "zoom", "skype")):
        return ("Comunicação", "message-circle")
    if any(k in n for k in ("spotify", "vlc", "obs", "steam", "epic", "game", "riot", "valorant", "minecraft", "xbox", "ea ", "ubisoft", "media", "audio")):
        return ("Mídia & Jogos", "gamepad-2")
    if any(k in n for k in ("word", "excel", "powerpoint", "notion", "obsidian", "acrobat", "pdf", "office", "libreoffice", "notas", "onenote")):
        return ("Produtividade", "file-text")
    if any(k in n for k in ("photoshop", "figma", "canva", "gimp", "blender", "inkscape", "paint", "illustrator", "premiere", "capcut")):
        return ("Criativo", "palette")
    return ("Instalados", "app-window")


def sync_installed_apps() -> Dict[str, Any]:
    """
    Scan the user's OS (Windows Start Menu, Desktop, Registry App Paths & Linux .desktop entries)
    and synchronize real installed applications into AURA OS SQLite database.
    """
    discovered: Dict[str, Dict[str, str]] = {}

    # 1. Include core built-in apps
    for key, info in KNOWN_APPS.items():
        discovered[key] = {
            "id": key,
            "name": info["name"],
            "target_path": info["win_cmd"] if IS_WINDOWS else (info["linux_cmd"][0] if info.get("linux_cmd") else key),
            "exe_name": str(info["win_cmd"]).split("\\")[-1].lower() if IS_WINDOWS else key,
            "category": info.get("cat", "Sistema"),
            "icon": info.get("icon", "box"),
            "source": "core",
        }

    ignore_words = (
        "uninstall", "desinstalar", "readme", "leia-me", "help", "ajuda", "website", "manual",
        "update", "updater", "setup", "installer", "configurar", "diagnostic", "repair", "license",
    )

    if IS_WINDOWS:
        # 2A. Scan Windows Start Menu & Desktop .lnk shortcuts
        scan_dirs = [
            Path(os.environ.get("ProgramData", "C:\\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            Path.home() / "Desktop",
        ]
        for base in scan_dirs:
            if not base.exists():
                continue
            try:
                for item in base.rglob("*.lnk"):
                    stem = item.stem.strip()
                    if len(stem) < 2 or len(stem) > 42:
                        continue
                    if any(w in stem.lower() for w in ignore_words):
                        continue
                    app_id = stem.lower().replace(" ", "_")
                    if app_id in discovered:
                        continue
                    cat, icon = _classify_app_metadata(stem)
                    discovered[app_id] = {
                        "id": app_id,
                        "name": stem,
                        "target_path": str(item),
                        "exe_name": stem.lower(),
                        "category": cat,
                        "icon": icon,
                        "source": "start_menu",
                    }
                    if len(discovered) >= 85:
                        break
            except Exception:
                continue

        # 2B. Scan Windows Registry App Paths for popular executables
        try:
            import winreg
            for root_hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(root_hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as k:
                        num_sub = winreg.QueryInfoKey(k)[0]
                        for i in range(min(num_sub, 80)):
                            sub_name = winreg.EnumKey(k, i)
                            if not sub_name.lower().endswith(".exe"):
                                continue
                            clean_stem = sub_name[:-4]
                            if any(w in clean_stem.lower() for w in ignore_words) or len(clean_stem) < 3:
                                continue
                            with winreg.OpenKey(k, sub_name) as sub_k:
                                val, _ = winreg.QueryValueEx(sub_k, "")
                                if val and os.path.exists(str(val).strip('"')):
                                    exe_path = str(val).strip('"')
                                    app_id = clean_stem.lower()
                                    if app_id not in discovered:
                                        cat, icon = _classify_app_metadata(clean_stem)
                                        discovered[app_id] = {
                                            "id": app_id,
                                            "name": clean_stem.capitalize(),
                                            "target_path": exe_path,
                                            "exe_name": sub_name.lower(),
                                            "category": cat,
                                            "icon": icon,
                                            "source": "registry",
                                        }
                except Exception:
                    continue
        except Exception:
            pass
    else:
        # 2C. Scan Linux Ubuntu .desktop files
        desktop_dirs = [
            Path("/usr/share/applications"),
            Path("/var/lib/snapd/desktop/applications"),
            Path.home() / ".local" / "share" / "applications",
        ]
        for base in desktop_dirs:
            if not base.exists():
                continue
            try:
                for item in base.glob("*.desktop"):
                    txt = item.read_text(encoding="utf-8", errors="ignore")
                    if "NoDisplay=true" in txt:
                        continue
                    name_val = ""
                    exec_val = ""
                    for line in txt.splitlines():
                        if line.startswith("Name=") and not name_val:
                            name_val = line.split("=", 1)[1].strip()
                        elif line.startswith("Exec=") and not exec_val:
                            exec_val = line.split("=", 1)[1].strip().split("%")[0].strip()
                    if name_val and exec_val and len(discovered) < 85:
                        app_id = name_val.lower().replace(" ", "_")
                        cat, icon = _classify_app_metadata(name_val)
                        discovered[app_id] = {
                            "id": app_id,
                            "name": name_val,
                            "target_path": exec_val,
                            "exe_name": exec_val.split()[0].split("/")[-1].lower(),
                            "category": cat,
                            "icon": icon,
                            "source": "desktop_entry",
                        }
            except Exception:
                continue

    batch_list = list(discovered.values())
    saved_count = save_synced_apps_batch(batch_list)
    log_activity("SYNC APPS", f"{saved_count} aplicativos sincronizados com o sistema")
    return {
        "success": True,
        "synced_count": saved_count,
        "apps": get_quick_apps_catalog(),
        "message": f"Sincronização concluída! **{saved_count} aplicativos** do seu computador foram mapeados e integrados à AURA.",
    }


def get_quick_apps_catalog() -> List[Dict[str, Any]]:
    """Return all synchronized apps enriched with real-time running status (PID & RAM) from the OS."""
    synced = list_synced_apps()
    if not synced:
        sync_installed_apps()
        synced = list_synced_apps()

    # Build map of running processes
    running_procs: Dict[str, Dict[str, Any]] = {}
    for proc in psutil.process_iter(["pid", "name", "memory_percent"]):
        try:
            pname = (proc.info["name"] or "").lower()
            if pname:
                stem = pname[:-4] if pname.endswith(".exe") else pname
                if stem not in running_procs or (proc.info["memory_percent"] or 0) > running_procs[stem]["mem"]:
                    running_procs[stem] = {
                        "pid": proc.info["pid"],
                        "exe": pname,
                        "mem": round(proc.info["memory_percent"] or 0.0, 1),
                    }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    enriched: List[Dict[str, Any]] = []
    for app in synced:
        app_name_low = app["name"].lower()
        exe_stem = (app.get("exe_name") or "").lower().replace(".exe", "")
        is_running = False
        matched_pid = None
        matched_mem = 0.0

        for r_stem, r_info in running_procs.items():
            if len(r_stem) >= 3 and (r_stem == exe_stem or r_stem == app["id"] or r_stem in app_name_low):
                is_running = True
                matched_pid = r_info["pid"]
                matched_mem = r_info["mem"]
                break

        enriched.append(
            {
                "id": app["id"],
                "name": app["name"],
                "icon": app["icon"],
                "category": app["category"],
                "target_path": app["target_path"],
                "source": app["source"],
                "running": is_running,
                "pid": matched_pid,
                "memory_percent": matched_mem,
            }
        )

    # Sort: Running apps first, then core apps, then alphabetical
    enriched.sort(key=lambda x: (not x["running"], x["source"] != "core", x["name"].lower()))
    return enriched


def check_installed_program(query: str) -> Dict[str, Any]:
    """
    Deeply verify whether a program, game, or CLI tool is installed on this computer.
    Checks: synchronized apps, running processes, Windows Uninstall Registry, Steam/Epic/Xbox/Program Files,
    and Linux PATH/.desktop entries.
    """
    q = query.strip().lower()
    if not q:
        return {"installed": False, "query": query, "matches": [], "checked_sources": [], "summary": "Nome vazio."}

    matches: List[Dict[str, str]] = []
    seen_keys = set()
    checked_sources: List[str] = []

    def add_match(name: str, source: str, location: str = ""):
        key = (name.lower().strip(), source)
        if key not in seen_keys:
            seen_keys.add(key)
            matches.append({"name": name, "source": source, "location": location})

    # 1. Check synchronized apps catalog (Start Menu, Desktop, App Paths)
    checked_sources.append("Apps Sincronizados (Menu Iniciar / Desktop / App Paths)")
    for app in get_quick_apps_catalog():
        if q in app["name"].lower() or q in app["id"].lower():
            status = f"Rodando agora (PID {app['pid']})" if app.get("running") else "Instalado"
            add_match(app["name"], f"Catálogo AURA ({status})", app.get("target_path", ""))

    # 2. Check running processes
    checked_sources.append("Processos em Execução")
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pname = proc.info["name"] or ""
            if q in pname.lower():
                add_match(pname, f"Processo Ativo (PID {proc.info['pid']})", "Em execução na memória")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # 3. Check PATH / CLI tools
    checked_sources.append("PATH do Sistema")
    which_hit = shutil.which(q)
    if which_hit:
        add_match(query.strip(), "Executável no PATH", which_hit)

    if IS_WINDOWS:
        # 4. Windows Uninstall Registry (catches Steam games, Epic, MSI, Setup installers)
        checked_sources.append("Registro de Programas Instalados do Windows")
        try:
            import winreg
            reg_paths = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            ]
            for hive, subkey in reg_paths:
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        for i in range(winreg.QueryInfoKey(key)[0]):
                            try:
                                sk_name = winreg.EnumKey(key, i)
                                with winreg.OpenKey(key, sk_name) as item_key:
                                    disp_name, _ = winreg.QueryValueEx(item_key, "DisplayName")
                                    if q in str(disp_name).lower() or (q in sk_name.lower()):
                                        loc = ""
                                        try:
                                            loc, _ = winreg.QueryValueEx(item_key, "InstallLocation")
                                        except Exception:
                                            pass
                                        add_match(str(disp_name), "Registro do Windows", str(loc or sk_name))
                            except Exception:
                                continue
                except Exception:
                    continue
        except Exception:
            pass

        # 5. Steam / Epic / Program Files / XboxGames folders
        checked_sources.append("Steam / Program Files / Pastas de Jogos")
        candidate_dirs = [
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")),
            Path("C:\\XboxGames"),
            Path("D:\\SteamLibrary\\steamapps\\common"),
            Path("E:\\SteamLibrary\\steamapps\\common"),
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Steam" / "steamapps" / "common",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Epic Games",
        ]
        for base in candidate_dirs:
            if not base.exists():
                continue
            try:
                for sub in base.iterdir():
                    if q in sub.name.lower():
                        add_match(sub.name, f"Pasta ({base.name})", str(sub))
            except Exception:
                continue
    else:
        checked_sources.append("Atalhos .desktop / Steam Linux")
        linux_steam = Path.home() / ".local" / "share" / "Steam" / "steamapps" / "common"
        if linux_steam.exists():
            for sub in linux_steam.iterdir():
                if q in sub.name.lower():
                    add_match(sub.name, "Steam Linux", str(sub))

    installed = len(matches) > 0
    if installed:
        lines = [f"• **{m['name']}** — *{m['source']}*" + (f" (`{m['location']}`)" if m.get("location") else "") for m in matches[:10]]
        summary = f"Sim! Encontrei **{len(matches)}** registro(s) para **{query.strip()}** instalado(s) no seu computador:\n\n" + "\n".join(lines)
    else:
        summary = (
            f"Não! Verifiquei o seu computador e **não encontrei \"{query.strip()}\" instalado**.\n\n"
            f"Locais verificados: {', '.join(checked_sources)}."
        )

    log_activity("VERIFICAÇÃO APP", f"Verificado '{query.strip()}': {'Encontrado' if installed else 'Não encontrado'}")
    return {
        "installed": installed,
        "query": query.strip(),
        "matches": matches,
        "checked_sources": checked_sources,
        "summary": summary,
    }



def take_screenshot(open_after: bool = False) -> Dict[str, Any]:
    """Cross-platform screen capture (Windows & Linux Ubuntu X11/Wayland)."""
    out_dir = Path.home() / "Pictures" / "Capturas_AURA"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = out_dir / f"captura_{ts}.png"

    try:
        captured = False
        if IS_LINUX:
            for cmd in (
                ["gnome-screenshot", "-f", str(filepath)],
                ["scrot", str(filepath)],
                ["import", "-window", "root", str(filepath)],
            ):
                if shutil.which(cmd[0]):
                    subprocess.run(cmd, timeout=8, check=False)
                    if filepath.exists():
                        captured = True
                        break
        if not captured:
            from PIL import ImageGrab
            img = ImageGrab.grab(all_screens=True if IS_WINDOWS else False)
            img.save(str(filepath), "PNG")

        if open_after:
            if IS_WINDOWS:
                os.startfile(str(filepath))
            else:
                subprocess.Popen(["xdg-open", str(filepath)])

        log_activity("CAPTURA", f"Screenshot salva: {filepath.name}")
        return {
            "success": True,
            "path": str(filepath),
            "filename": filepath.name,
            "url": f"/api/system/screenshot-file/{filepath.name}",
            "message": f"Captura de tela salva em `{filepath}`!",
        }
    except Exception as e:
        return {"success": False, "message": f"Erro ao capturar tela: {e}"}


def media_and_volume_control(action: str) -> Dict[str, Any]:
    """Cross-platform volume & media control for Windows (Win32 VK) and Linux Ubuntu (pactl/amixer/playerctl)."""
    act = action.lower().strip()

    if IS_WINDOWS:
        import ctypes
        VK_MAP = {
            "vol_up": (0xAF, 5, "Volume aumentado no Windows!"),
            "vol_down": (0xAE, 5, "Volume reduzido no Windows!"),
            "mute": (0xAD, 1, "Áudio alternado (Mudo/Ativo)!"),
            "play_pause": (0xB3, 1, "Play/Pause de mídia enviado!"),
            "next_track": (0xB0, 1, "Próxima faixa de mídia!"),
            "prev_track": (0xB1, 1, "Faixa anterior de mídia!"),
        }
        if act not in VK_MAP:
            return {"success": False, "message": f"Ação desconhecida: {action}"}
        vk_code, repeats, msg = VK_MAP[act]
        try:
            user32 = ctypes.windll.user32
            for _ in range(repeats):
                user32.keybd_event(vk_code, 0, 0, 0)
                user32.keybd_event(vk_code, 0, 2, 0)
            log_activity("MÍDIA", msg)
            return {"success": True, "action": act, "message": msg}
        except Exception as e:
            return {"success": False, "message": f"Erro de mídia: {e}"}
    else:
        # Linux Ubuntu PulseAudio / PipeWire (pactl) & ALSA (amixer) & playerctl
        LINUX_CMDS = {
            "vol_up": ("pactl set-sink-volume @DEFAULT_SINK@ +10% || amixer set Master 10%+", "Volume aumentado no Ubuntu!"),
            "vol_down": ("pactl set-sink-volume @DEFAULT_SINK@ -10% || amixer set Master 10%-", "Volume reduzido no Ubuntu!"),
            "mute": ("pactl set-sink-mute @DEFAULT_SINK@ toggle || amixer set Master toggle", "Mudo alternado no Ubuntu!"),
            "play_pause": ("playerctl play-pause || xdotool key XF86AudioPlay", "Play/Pause enviado no Ubuntu!"),
            "next_track": ("playerctl next || xdotool key XF86AudioNext", "Próxima faixa enviada!"),
            "prev_track": ("playerctl previous || xdotool key XF86AudioPrev", "Faixa anterior enviada!"),
        }
        if act not in LINUX_CMDS:
            return {"success": False, "message": f"Ação desconhecida: {action}"}
        cmd_str, msg = LINUX_CMDS[act]
        try:
            subprocess.Popen(cmd_str, shell=True)
            log_activity("MÍDIA", msg)
            return {"success": True, "action": act, "message": msg}
        except Exception as e:
            return {"success": False, "message": f"Erro de mídia no Linux: {e}"}


def clean_temp_files() -> Dict[str, Any]:
    """Clean temporary files safely on Windows (%TEMP%) or Linux Ubuntu (~/.cache/thumbnails & /tmp)."""
    target_dirs: List[Path] = []
    if IS_WINDOWS:
        target_dirs.append(Path(os.environ.get("TEMP", "")))
    else:
        target_dirs.append(Path.home() / ".cache" / "thumbnails")
        target_dirs.append(Path("/tmp"))

    removed_files = 0
    freed_bytes = 0

    for temp_dir in target_dirs:
        if not temp_dir.exists():
            continue
        for item in temp_dir.iterdir():
            try:
                # On Linux /tmp, only clean files owned by current user
                if not IS_WINDOWS and temp_dir == Path("/tmp"):
                    if item.stat().st_uid != os.getuid():
                        continue
                if item.is_file():
                    sz = item.stat().st_size
                    item.unlink()
                    removed_files += 1
                    freed_bytes += sz
                elif item.is_dir():
                    sz = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                    shutil.rmtree(item, ignore_errors=False)
                    removed_files += 1
                    freed_bytes += sz
            except Exception:
                continue

    freed_mb = round(freed_bytes / (1024 * 1024), 2)
    log_activity("LIMPEZA", f"Limpeza TEMP: {removed_files} itens ({freed_mb} MB liberados)")
    return {
        "success": True,
        "removed_items": removed_files,
        "freed_mb": freed_mb,
        "message": f"Limpeza concluída! Removi **{removed_files}** itens temporários, liberando **{freed_mb} MB**.",
    }


def empty_recycle_bin() -> Dict[str, Any]:
    """Empty Recycle Bin on Windows or ~/.local/share/Trash on Linux Ubuntu."""
    try:
        if IS_WINDOWS:
            import ctypes
            ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x01 | 0x02 | 0x04)
        else:
            trash_dir = Path.home() / ".local" / "share" / "Trash"
            for sub in ("files", "info"):
                p = trash_dir / sub
                if p.exists():
                    shutil.rmtree(p, ignore_errors=True)
                    p.mkdir(parents=True, exist_ok=True)
        log_activity("SISTEMA", "Lixeira esvaziada")
        return {"success": True, "message": "Lixeira do sistema esvaziada com sucesso!"}
    except Exception as e:
        return {"success": False, "message": f"Erro ao esvaziar lixeira: {e}"}


def lock_workstation() -> Dict[str, Any]:
    """Lock screen on Windows or Linux Ubuntu."""
    try:
        if IS_WINDOWS:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
        else:
            subprocess.Popen(
                "loginctl lock-session || xdg-screensaver lock || gnome-screensaver-command -l",
                shell=True,
            )
        log_activity("SEGURANÇA", "Tela bloqueada")
        return {"success": True, "message": "Tela do computador bloqueada com segurança."}
    except Exception as e:
        return {"success": False, "message": f"Erro ao bloquear tela: {e}"}


def run_productivity_routine(routine_id: str) -> Dict[str, Any]:
    rid = routine_id.lower().strip()
    steps_done: List[str] = []

    if rid == "modo_dev":
        r1 = open_application("vscode")
        steps_done.append(f"IDE/Editor: {'OK' if r1.get('success') else r1.get('message')}")
        r2 = open_application("terminal")
        steps_done.append(f"Terminal: {'OK' if r2.get('success') else r2.get('message')}")
        r3 = open_application("github")
        steps_done.append(f"GitHub: {'OK' if r3.get('success') else r3.get('message')}")
        msg = "**Rotina Modo Dev ativada!**\n• " + "\n• ".join(steps_done)
    elif rid == "modo_estudo":
        open_application("bloco de notas")
        steps_done.append("Editor de Texto aberto")
        open_application("https://pt.wikipedia.org")
        steps_done.append("Wikipédia aberta")
        msg = "**Rotina Modo Estudo ativada:** Editor de Notas e Wikipédia prontos!"
    elif rid == "modo_faxina":
        temp_res = clean_temp_files()
        steps_done.append(f"TEMP limpo ({temp_res.get('freed_mb', 0)} MB)")
        from file_tools import organize_directory
        org_res = organize_directory("downloads", dry_run=False)
        steps_done.append(f"Downloads organizados ({org_res.get('total_files', 0)} arq.)")
        msg = (
            f"**Rotina Faxina Completa concluída!**\n"
            f"• Temporários removidos: **{temp_res.get('removed_items', 0)}** ({temp_res.get('freed_mb', 0)} MB liberados)\n"
            f"• Downloads organizados: **{org_res.get('total_files', 0)}** arquivo(s)"
        )
    else:
        return {"success": False, "message": f"Rotina desconhecida: {routine_id}"}

    log_activity("ROTINA", f"Rotina '{rid}' executada")
    return {"success": True, "routine": rid, "steps": steps_done, "message": msg}


# --- Cross-Platform Background Autostart (Windows + Linux Ubuntu) ---

def get_autostart_file_path() -> Path:
    if IS_WINDOWS:
        startup_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        return startup_dir / "AURA_Assistente_Background.vbs"
    else:
        autostart_dir = Path.home() / ".config" / "autostart"
        return autostart_dir / "aura-os.desktop"


def get_background_status() -> Dict[str, Any]:
    autostart_file = get_autostart_file_path()
    desktop_dir = Path.home() / "Desktop"
    desktop_file = desktop_dir / ("Iniciar AURA (2º Plano).vbs" if IS_WINDOWS else "AURA_OS.desktop")
    return {
        "os": OS_NAME,
        "autostart_enabled": autostart_file.exists(),
        "startup_path": str(autostart_file),
        "desktop_shortcut_exists": desktop_file.exists(),
    }


def toggle_windows_autostart(enable: bool) -> Dict[str, Any]:
    """Enable or disable background autostart on both Windows (.vbs) and Linux Ubuntu (.desktop)."""
    autostart_file = get_autostart_file_path()
    project_dir = Path(__file__).parent
    widget_py = project_dir / "desktop_widget.py"

    try:
        if enable:
            autostart_file.parent.mkdir(parents=True, exist_ok=True)
            if IS_WINDOWS:
                content = (
                    'Set WshShell = CreateObject("WScript.Shell")\n'
                    f'WshShell.CurrentDirectory = "{project_dir}"\n'
                    f'WshShell.Run "pythonw.exe ""{widget_py}""", 0, False\n'
                )
            else:
                content = (
                    "[Desktop Entry]\n"
                    "Type=Application\n"
                    "Name=AURA OS Background Assistant\n"
                    "Comment=Barra Flutuante e Orquestrador Multi-Agente AURA\n"
                    f"Exec={sys.executable} {widget_py}\n"
                    f"Path={project_dir}\n"
                    "Terminal=false\n"
                    "X-GNOME-Autostart-enabled=true\n"
                )
            autostart_file.write_text(content, encoding="utf-8")
            log_activity("SEGUNDO PLANO", f"Autostart ativado ({OS_NAME})")
            return {
                "success": True,
                "autostart_enabled": True,
                "message": f"Inicialização automática em 2º plano ATIVADA no {OS_NAME}!",
            }
        else:
            if autostart_file.exists():
                autostart_file.unlink()
            log_activity("SEGUNDO PLANO", f"Autostart desativado ({OS_NAME})")
            return {
                "success": True,
                "autostart_enabled": False,
                "message": "Inicialização automática em 2º plano desativada.",
            }
    except Exception as e:
        return {"success": False, "message": f"Erro ao configurar inicialização: {e}"}


def create_desktop_launcher() -> Dict[str, Any]:
    """Create a 1-click desktop launcher for Windows or Linux Ubuntu."""
    project_dir = Path(__file__).parent
    widget_py = project_dir / "desktop_widget.py"
    desktop_dir = Path.home() / "Desktop"
    desktop_dir.mkdir(parents=True, exist_ok=True)

    try:
        if IS_WINDOWS:
            target = desktop_dir / "Iniciar AURA (2º Plano).vbs"
            content = (
                'Set WshShell = CreateObject("WScript.Shell")\n'
                f'WshShell.CurrentDirectory = "{project_dir}"\n'
                f'WshShell.Run "pythonw.exe ""{widget_py}""", 0, False\n'
            )
            target.write_text(content, encoding="utf-8")
        else:
            target = desktop_dir / "AURA_OS.desktop"
            content = (
                "[Desktop Entry]\n"
                "Version=1.0\n"
                "Type=Application\n"
                "Name=AURA OS 3.0\n"
                "Comment=Assistente e Orquestrador Multi-Agente\n"
                f"Exec={sys.executable} {widget_py}\n"
                f"Path={project_dir}\n"
                "Terminal=false\n"
                "Categories=Utility;Application;\n"
            )
            target.write_text(content, encoding="utf-8")
            os.chmod(str(target), 0o755)

        log_activity("ATALHO", f"Atalho criado: {target.name}")
        return {
            "success": True,
            "path": str(target),
            "message": f"Atalho **'{target.name}'** criado na Área de Trabalho!",
        }
    except Exception as e:
        return {"success": False, "message": f"Erro ao criar atalho: {e}"}


def get_network_diagnostics() -> Dict[str, Any]:
    """Scan active local TCP ports, test internet latency (ms), and check connectivity."""
    common_ports = [
        (80, "HTTP Web"),
        (443, "HTTPS"),
        (3000, "Dev Server (Node/React)"),
        (5173, "Vite Frontend"),
        (5432, "PostgreSQL"),
        (6379, "Redis"),
        (8000, "Python / Django / FastAPI"),
        (8080, "Proxy / Web Alt"),
        (8765, "AURA OS 5.0 Server"),
        (11434, "Ollama Local AI"),
    ]
    open_ports: List[Dict[str, Any]] = []
    for port, label in common_ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.08)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    open_ports.append({"port": port, "service": label})
        except Exception:
            pass

    # Measure TCP handshake latency to Cloudflare DNS (1.1.1.1:53) & Google DNS (8.8.8.8:53)
    latency_ms = -1.0
    for host in ("1.1.1.1", "8.8.8.8"):
        try:
            t0 = time.perf_counter()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.2)
                s.connect((host, 53))
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            break
        except Exception:
            continue

    return {
        "online": latency_ms >= 0,
        "latency_ms": latency_ms if latency_ms >= 0 else 0,
        "lan_ip": get_lan_ip(),
        "hostname": socket.gethostname(),
        "open_ports": open_ports,
    }


def power_control(action: str, delay_minutes: int = 30) -> Dict[str, Any]:
    """Cross-platform power actions: lock, sleep, schedule_shutdown, cancel_shutdown."""
    act = action.lower().strip()
    try:
        if act == "lock":
            return lock_workstation()
        elif act == "sleep":
            if IS_WINDOWS:
                subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
            else:
                subprocess.Popen("systemctl suspend", shell=True)
            log_activity("ENERGIA", "Modo Suspensão acionado")
            return {"success": True, "message": "Computador entrando em modo de suspensão..."}
        elif act == "schedule_shutdown":
            secs = max(60, int(delay_minutes) * 60)
            if IS_WINDOWS:
                subprocess.run(["shutdown", "/s", "/t", str(secs)], check=False)
            else:
                subprocess.run(["shutdown", f"+{max(1, int(delay_minutes))}"], check=False)
            log_activity("ENERGIA", f"Desligamento agendado para {delay_minutes} min")
            return {"success": True, "message": f"Desligamento automático agendado para daqui a **{delay_minutes} minutos**."}
        elif act == "cancel_shutdown":
            if IS_WINDOWS:
                subprocess.run(["shutdown", "/a"], check=False)
            else:
                subprocess.run(["shutdown", "-c"], check=False)
            log_activity("ENERGIA", "Desligamento agendado cancelado")
            return {"success": True, "message": "Qualquer desligamento agendado foi **cancelado** com sucesso!"}
        return {"success": False, "message": f"Ação de energia desconhecida: {action}"}
    except Exception as e:
        return {"success": False, "message": f"Erro de energia: {e}"}


def get_top_processes(limit: int = 25, sort_by: str = "cpu") -> List[Dict[str, Any]]:
    """Return top running processes sorted by CPU or RAM usage."""
    procs: List[Dict[str, Any]] = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "status"]):
        try:
            info = p.info
            mem_mb = round((info["memory_info"].rss if info.get("memory_info") else 0) / (1024 * 1024), 1)
            procs.append({
                "pid": info["pid"],
                "name": info.get("name") or "unknown",
                "cpu_percent": round(float(info.get("cpu_percent") or 0.0), 1),
                "memory_mb": mem_mb,
                "status": info.get("status") or "running",
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    key = "memory_mb" if sort_by == "ram" else "cpu_percent"
    procs.sort(key=lambda x: (x[key], x["memory_mb"]), reverse=True)
    return procs[: max(1, min(limit, 100))]


def kill_process_by_pid(pid: int) -> Dict[str, Any]:
    """Safely terminate a running process by PID."""
    if pid <= 0 or pid == os.getpid():
        return {"success": False, "message": "PID inválido ou protegido (processo atual da AURA)."}
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except psutil.TimeoutExpired:
            proc.kill()
        log_activity("PROCESSOS", f"Processo encerrado: {name} (PID {pid})")
        return {"success": True, "message": f"Processo **{name}** (PID `{pid}`) encerrado com sucesso."}
    except psutil.NoSuchProcess:
        return {"success": False, "message": f"Processo PID {pid} não encontrado."}
    except psutil.AccessDenied:
        return {"success": False, "message": f"Permissão negada para encerrar PID {pid}."}
    except Exception as e:
        return {"success": False, "message": f"Erro ao encerrar PID {pid}: {e}"}


def get_open_ports(limit: int = 35) -> List[Dict[str, Any]]:
    """Return active listening TCP/UDP network ports with owning process name and PID."""
    ports: List[Dict[str, Any]] = []
    seen = set()
    try:
        conns = psutil.net_connections(kind="inet")
    except Exception:
        return []

    proc_cache: Dict[int, str] = {}
    for c in conns:
        try:
            if c.status not in ("LISTEN", "NONE", "") and c.type == socket.SOCK_STREAM:
                continue
            if not c.laddr:
                continue
            ip = c.laddr.ip
            port = c.laddr.port
            proto = "TCP" if c.type == socket.SOCK_STREAM else "UDP"
            key = (proto, ip, port, c.pid)
            if key in seen:
                continue
            seen.add(key)
            pid = c.pid or 0
            if pid and pid not in proc_cache:
                try:
                    proc_cache[pid] = psutil.Process(pid).name()
                except Exception:
                    proc_cache[pid] = "system"
            ports.append(
                {
                    "protocol": proto,
                    "ip": ip,
                    "port": port,
                    "pid": pid,
                    "process": proc_cache.get(pid, "system"),
                    "status": c.status or "LISTEN",
                }
            )
        except Exception:
            continue

    ports.sort(key=lambda x: x["port"])
    return ports[: max(1, min(limit, 100))]


def get_dev_environment_info() -> Dict[str, Any]:
    """Detect installed developer runtimes and CLI tools with versions."""
    tools = {
        "python": ["python", "--version"],
        "node": ["node", "--version"],
        "npm": ["npm", "--version"],
        "git": ["git", "--version"],
        "gh": ["gh", "--version"],
        "docker": ["docker", "--version"],
    }
    if IS_WINDOWS:
        tools["winget"] = ["winget", "--version"]

    results: Dict[str, Dict[str, Any]] = {}
    for name, cmd in tools.items():
        exe_path = shutil.which(cmd[0])
        if not exe_path:
            results[name] = {"installed": False, "version": "", "path": ""}
            continue
        version_str = ""
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            raw = (proc.stdout or proc.stderr or "").strip().splitlines()
            if raw:
                version_str = raw[0][:80]
        except Exception:
            version_str = "instalado"
        results[name] = {"installed": True, "version": version_str, "path": exe_path}
    return {"ok": True, "os": OS_NAME, "tools": results}



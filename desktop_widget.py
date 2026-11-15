import os
import sys
import time
import socket
import threading
import subprocess
import webbrowser
from pathlib import Path

from PIL import Image, ImageDraw
import pystray

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from storage import init_db
from system_tools import IS_WINDOWS
from remote_bridge import start_cloud_relay_listener, start_public_internet_tunnel
from automation_engine import start_automation_and_clipboard_daemons
from updater import start_auto_update_daemon

API_URL = "http://127.0.0.1:8765"
HUD_URL = "http://127.0.0.1:8765/hud"

COMPACT_W = 735
COMPACT_H = 52
EXPANDED_W = 750
EXPANDED_H = 510

# Keep window & state at module level so pywebview's js_api introspection
# NEVER traverses the .NET WinForms/WebView2 object graph!
_HUD_STATE = {
    "window": None,
    "is_expanded": False,
    "is_visible": True,
    "screen_w": 1920,
}

if IS_WINDOWS:
    try:
        import ctypes
        _HUD_STATE["screen_w"] = ctypes.windll.user32.GetSystemMetrics(0)
    except Exception:
        pass


def is_port_in_use(port: int = 8765) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.35)
        return s.connect_ex(("127.0.0.1", port)) == 0


def ensure_backend_server():
    """Start FastAPI server on 0.0.0.0:8765 + Cloud Relay + Public Tunnel + Daemons in background."""
    init_db()
    start_cloud_relay_listener()
    start_public_internet_tunnel()
    start_automation_and_clipboard_daemons()
    start_auto_update_daemon()
    if is_port_in_use(8765):
        return

    def _run():
        import uvicorn
        from app import app

        uvicorn.run(app, host="0.0.0.0", port=8765, log_level="warning")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    for _ in range(25):
        if is_port_in_use(8765):
            break
        time.sleep(0.15)


def open_standalone_app_window(path_suffix: str = ""):
    target_url = f"{API_URL}{path_suffix}"
    if IS_WINDOWS:
        candidates = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for exe in candidates:
            if os.path.exists(exe):
                try:
                    subprocess.Popen([exe, f"--app={target_url}", "--window-size=1360,860"])
                    return
                except Exception:
                    pass
    else:
        for cmd in ("google-chrome", "chromium-browser", "chromium", "microsoft-edge"):
            if subprocess.call(f"command -v {cmd} >/dev/null 2>&1", shell=True) == 0:
                try:
                    subprocess.Popen([cmd, f"--app={target_url}", "--window-size=1360,860"])
                    return
                except Exception:
                    pass
    webbrowser.open(target_url)


def create_tray_icon_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((4, 4, 60, 60), radius=18, fill=(6, 10, 21, 255), outline=(56, 189, 248, 255), width=3)
    draw.ellipse((16, 16, 48, 48), outline=(129, 140, 248, 255), width=3)
    draw.ellipse((25, 25, 39, 39), fill=(56, 189, 248, 255))
    return img


def apply_hud_geometry(expanded: bool, sync_js: bool = False):
    _HUD_STATE["is_expanded"] = bool(expanded)
    win = _HUD_STATE.get("window")
    if not win:
        return
    w = EXPANDED_W if _HUD_STATE["is_expanded"] else COMPACT_W
    h = EXPANDED_H if _HUD_STATE["is_expanded"] else COMPACT_H
    x = (_HUD_STATE["screen_w"] - w) // 2
    try:
        win.resize(w, h)
        win.move(x, 6)
        if sync_js:
            js_bool = "true" if _HUD_STATE["is_expanded"] else "false"
            win.evaluate_js(f"if(window.setDrawerState) window.setDrawerState({js_bool}, false);")
    except Exception:
        pass


def hud_control_dispatch(action: str) -> dict:
    """Handle HUD control commands from JS API, FastAPI endpoints, Tray, or Hotkey."""
    win = _HUD_STATE.get("window")
    if not win:
        return {"ok": False, "active": False}

    if action == "expand":
        _HUD_STATE["is_visible"] = True
        win.show()
        apply_hud_geometry(True, sync_js=True)
    elif action == "collapse":
        apply_hud_geometry(False, sync_js=True)
    elif action == "toggle":
        if not _HUD_STATE["is_visible"]:
            _HUD_STATE["is_visible"] = True
            win.show()
            apply_hud_geometry(True, sync_js=True)
        else:
            apply_hud_geometry(not _HUD_STATE["is_expanded"], sync_js=True)
    elif action == "show":
        _HUD_STATE["is_visible"] = True
        win.show()
        apply_hud_geometry(_HUD_STATE["is_expanded"], sync_js=True)
    elif action == "hide":
        _HUD_STATE["is_visible"] = False
        win.hide()
    elif action == "open_app":
        open_standalone_app_window("")

    return {"ok": True, "active": True, "expanded": _HUD_STATE["is_expanded"], "visible": _HUD_STATE["is_visible"]}


class JsHudBridge:
    """
    JS-to-Python API exposed inside the CSS3 pywebview Top-Center HUD.
    IMPORTANT: Keep zero public attributes on `self` so pywebview never traverses WinForms objects.
    """

    def set_expanded(self, expanded: bool):
        apply_hud_geometry(bool(expanded), sync_js=False)
        return {"expanded": bool(expanded)}

    def toggle_expand(self):
        return hud_control_dispatch("toggle")

    def hide_to_tray(self):
        return hud_control_dispatch("hide")

    def show_from_tray(self):
        return hud_control_dispatch("show")

    def open_full_app(self):
        open_standalone_app_window("")
        return {"opened": True}


def start_system_tray():
    def _on_show(icon, item):
        hud_control_dispatch("show")

    def _on_expand(icon, item):
        hud_control_dispatch("expand")

    def _on_open_full(icon, item):
        open_standalone_app_window("")

    def _on_quit(icon, item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Mostrar Barra CSS no Topo (Ctrl+Shift+A)", _on_show, default=True),
        pystray.MenuItem("Expandir Painel AURA 4.0", _on_expand),
        pystray.MenuItem("Abrir Quadro Maestri 2D Completo", _on_open_full),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Encerrar AURA OS", _on_quit),
    )
    tray_icon = pystray.Icon("AURA", create_tray_icon_image(), "AURA OS 4.0 — Maestri & 2º Plano", menu)
    threading.Thread(target=tray_icon.run, daemon=True).start()


def start_global_hotkey_win32():
    if not IS_WINDOWS:
        return
    import ctypes
    from ctypes import wintypes

    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    VK_A = 0x41
    WM_HOTKEY = 0x0312
    HOTKEY_ID = 101

    def _loop():
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_SHIFT, VK_A):
            return
        msg = wintypes.MSG()
        try:
            while user32.GetMessageA(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    hud_control_dispatch("toggle")
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageA(ctypes.byref(msg))
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)

    threading.Thread(target=_loop, daemon=True).start()


def on_hud_startup(win):
    """Ensure exact compact frameless dimensions once WinForms removes the titlebar."""
    time.sleep(0.15)
    apply_hud_geometry(False, sync_js=True)


if __name__ == "__main__":
    ensure_backend_server()
    try:
        from app import register_hud_dispatcher
        register_hud_dispatcher(hud_control_dispatch)
    except Exception:
        pass

    bridge = JsHudBridge()
    start_system_tray()
    start_global_hotkey_win32()

    import webview

    x_pos = (_HUD_STATE["screen_w"] - COMPACT_W) // 2
    win = webview.create_window(
        title="AURA OS 4.0 HUD",
        url=HUD_URL,
        js_api=bridge,
        width=COMPACT_W,
        height=COMPACT_H,
        min_size=(300, 44),
        x=x_pos,
        y=6,
        frameless=True,
        shadow=False,
        on_top=True,
        easy_drag=False,
        background_color="#060a15",
    )
    _HUD_STATE["window"] = win
    webview.start(on_hud_startup, win)

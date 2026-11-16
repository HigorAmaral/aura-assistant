import os
import re
import time
import uuid
import json
import shutil
import threading
import subprocess
from datetime import datetime
from typing import Dict, Any, List, Optional

import httpx
from storage import get_settings, update_settings, log_activity
from system_tools import get_lan_ip, IS_WINDOWS

# In-memory live notification feed for connected mobile clients
_NOTIFICATIONS: List[Dict[str, Any]] = []
_TUNNEL_STATE: Dict[str, Any] = {
    "status": "stopped",  # 'stopped', 'starting', 'online', 'error'
    "public_url": "",
    "mobile_public_url": "",
    "provider": "",
    "error": "",
}
_tunnel_proc: Optional[subprocess.Popen] = None
_cloud_relay_started = False


def get_or_create_cloud_channel() -> str:
    """Get or generate a unique cloud channel ID for cross-network notifications & relay."""
    s = get_settings()
    channel = s.get("cloud_channel_id", "")
    if not channel:
        short_id = uuid.uuid4().hex[:10]
        channel = f"aura-pc-{short_id}"
        update_settings({"cloud_channel_id": channel})
    return channel


def push_mobile_notification(
    title: str,
    body: str,
    category: str = "AURA",
    agent_name: str = "AURA",
) -> Dict[str, Any]:
    """
    Send a real-time notification to the user's smartphone:
    1. Pushes to the local/tunnel Mobile Web App notification stream.
    2. Pushes over the internet via ntfy.sh Cloud Push so it reaches 4G/5G phones anywhere!
    """
    now_str = datetime.now().strftime("%H:%M:%S")
    notif = {
        "id": int(time.time() * 1000),
        "title": title,
        "body": body[:400],
        "category": category,
        "agent": agent_name,
        "timestamp": now_str,
    }
    _NOTIFICATIONS.insert(0, notif)
    del _NOTIFICATIONS[40:]  # Keep latest 40 notifications

    channel = get_or_create_cloud_channel()

    def _send_cloud_push():
        try:
            with httpx.Client(timeout=8.0) as client:
                # 1. Push human-readable notification to ntfy channel (for ntfy mobile app & SSE)
                client.post(
                    f"https://ntfy.sh/{channel}",
                    content=body[:350].encode("utf-8"),
                    headers={
                        "Title": title[:100],
                        "Priority": "high",
                        "Tags": "sparkles,computer",
                    },
                )
                # 2. Push structured JSON event to -events channel for the Mobile Remote Cloud Web App
                client.post(
                    f"https://ntfy.sh/{channel}-events",
                    content=json.dumps(notif, ensure_ascii=False).encode("utf-8"),
                )
        except Exception:
            pass

    threading.Thread(target=_send_cloud_push, daemon=True).start()
    log_activity("NOTIFICAÇÃO MOBILE", f"{title}: {body[:60]}")
    return notif


def get_mobile_notifications(since_id: int = 0) -> List[Dict[str, Any]]:
    if since_id <= 0:
        return _NOTIFICATIONS[:15]
    return [n for n in _NOTIFICATIONS if n["id"] > since_id]


def start_public_internet_tunnel() -> Dict[str, Any]:
    """
    Start a public HTTPS tunnel (via cloudflared if installed, or built-in OpenSSH localhost.run)
    so the user's smartphone can access AURA OS from 4G/5G or any external Wi-Fi network!
    """
    global _tunnel_proc
    if _TUNNEL_STATE["status"] == "online" and _TUNNEL_STATE["public_url"]:
        return get_remote_connection_info()

    _TUNNEL_STATE["status"] = "starting"
    _TUNNEL_STATE["error"] = ""

    def _tunnel_worker():
        global _tunnel_proc
        try:
            # Option A: Try cloudflared if available on PATH
            cf_bin = shutil.which("cloudflared")
            if cf_bin:
                _TUNNEL_STATE["provider"] = "Cloudflare Quick Tunnel"
                cmd = [cf_bin, "tunnel", "--url", "http://127.0.0.1:8765"]
                creationflags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
                _tunnel_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=creationflags,
                )
                if _tunnel_proc.stdout:
                    for line in _tunnel_proc.stdout:
                        m = re.search(r"(https://[a-zA-Z0-9-]+\.trycloudflare\.com)", line)
                        if m:
                            pub = m.group(1)
                            _TUNNEL_STATE["public_url"] = pub
                            _TUNNEL_STATE["mobile_public_url"] = f"{pub}/mobile"
                            _TUNNEL_STATE["status"] = "online"
                            log_activity("TÚNEL REMOTO", f"Túnel público ativo: {pub}/mobile")
                            push_mobile_notification(
                                "Acesso Remoto 4G/5G Ativado",
                                f"Acesse de qualquer rede: {pub}/mobile",
                                category="REMOTO",
                            )
                            break

            # Option B: Built-in OpenSSH reverse tunnel via localhost.run (available on Windows 10/11 & Ubuntu)
            ssh_bin = shutil.which("ssh")
            if ssh_bin and _TUNNEL_STATE["status"] != "online":
                _TUNNEL_STATE["provider"] = "OpenSSH Public Tunnel (localhost.run)"
                cmd = [
                    ssh_bin,
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null" if not IS_WINDOWS else "UserKnownHostsFile=NUL",
                    "-o", "ServerAliveInterval=30",
                    "-R", "80:127.0.0.1:8765",
                    "nokey@localhost.run",
                ]
                creationflags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
                _tunnel_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    creationflags=creationflags,
                )
                if _tunnel_proc.stdout:
                    for line in _tunnel_proc.stdout:
                        m = re.search(r"(https://[a-zA-Z0-9-]+\.lhr\.life)", line)
                        if m:
                            pub = m.group(1)
                            _TUNNEL_STATE["public_url"] = pub
                            _TUNNEL_STATE["mobile_public_url"] = f"{pub}/mobile"
                            _TUNNEL_STATE["status"] = "online"
                            log_activity("TÚNEL REMOTO", f"Túnel público ativo: {pub}/mobile")
                            push_mobile_notification(
                                "Acesso Remoto 4G/5G Ativado",
                                f"Acesse de qualquer lugar: {pub}/mobile",
                                category="REMOTO",
                            )
                            break

            if _TUNNEL_STATE["status"] != "online":
                _TUNNEL_STATE["status"] = "cloud_relay_only"
                _TUNNEL_STATE["provider"] = "AURA Cloud Relay (ntfy.sh Pub/Sub)"
        except Exception as e:
            _TUNNEL_STATE["status"] = "cloud_relay_only"
            _TUNNEL_STATE["error"] = str(e)

    threading.Thread(target=_tunnel_worker, daemon=True).start()
    return get_remote_connection_info()


def start_cloud_relay_listener():
    """
    Listen for remote commands sent from the smartphone over 4G/5G via the Cloud Relay channel
    (`https://ntfy.sh/<channel>-cmd/json`). This works from ANY network in the world even without port forwarding!
    """
    global _cloud_relay_started
    if _cloud_relay_started:
        return
    _cloud_relay_started = True
    channel = get_or_create_cloud_channel()

    def _listen_loop():
        from ai_engine import process_chat_message
        url = f"https://ntfy.sh/{channel}-cmd/json"
        while True:
            try:
                with httpx.Client(timeout=None) as client:
                    with client.stream("GET", url) as resp:
                        for line in resp.iter_lines():
                            if not line:
                                continue
                            data = json.loads(line)
                            if data.get("event") == "message":
                                raw_msg = data.get("message", "").strip()
                                if not raw_msg:
                                    continue
                                res = process_chat_message(raw_msg)
                                push_mobile_notification(
                                    title=f"Resposta AURA ({res.get('provider', 'IA')})",
                                    body=res.get("reply", "Comando concluído!"),
                                    category="COMANDO REMOTO",
                                )
            except Exception:
                time.sleep(5)

    threading.Thread(target=_listen_loop, daemon=True).start()


def get_remote_connection_info() -> Dict[str, Any]:
    lan_ip = get_lan_ip()
    channel = get_or_create_cloud_channel()
    lan_mobile_url = f"http://{lan_ip}:8765/mobile"
    pub_mobile_url = _TUNNEL_STATE.get("mobile_public_url") or ""

    return {
        "lan_ip": lan_ip,
        "lan_mobile_url": lan_mobile_url,
        "tunnel_status": _TUNNEL_STATE["status"],
        "tunnel_provider": _TUNNEL_STATE["provider"],
        "public_mobile_url": pub_mobile_url,
        "cloud_channel": channel,
        "ntfy_topic_url": f"https://ntfy.sh/{channel}",
        "active_qr_url": pub_mobile_url if pub_mobile_url else lan_mobile_url,
    }

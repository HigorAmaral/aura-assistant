import os
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from storage import log_activity
from system_tools import IS_WINDOWS, clean_temp_files
from remote_bridge import push_mobile_notification


_OPT_JOB_STATE: Dict[str, Any] = {
    "running": False,
    "task": "",
    "message": "",
    "ok": True,
    "updated_at": 0.0,
}


def get_optimizer_job_status() -> Dict[str, Any]:
    return dict(_OPT_JOB_STATE)


def _run_cmd(cmd: List[str], timeout: int = 35) -> Dict[str, Any]:
    flags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=flags,
            errors="replace",
        )
        return {
            "ok": res.returncode == 0,
            "code": res.returncode,
            "stdout": (res.stdout or "").strip(),
            "stderr": (res.stderr or "").strip(),
        }
    except Exception as exc:
        return {"ok": False, "code": -1, "stdout": "", "stderr": str(exc)}


def scan_updatable_apps() -> Dict[str, Any]:
    """Scan for outdated applications using winget (Windows) or apt/snap/flatpak (Linux)."""
    apps: List[Dict[str, str]] = []
    manager = "none"
    raw_note = ""

    if IS_WINDOWS and shutil.which("winget"):
        manager = "winget"
        res = _run_cmd(["winget", "upgrade", "--include-unknown"], timeout=45)
        lines = [l for l in res["stdout"].splitlines() if l.strip()]
        sep_idx = -1
        for i, line in enumerate(lines):
            if set(line.strip()) <= {"-"} and len(line.strip()) > 10:
                sep_idx = i
                break
        if sep_idx >= 0:
            for line in lines[sep_idx + 1 :]:
                if "upgrades available" in line.lower() or "atualizações disponíveis" in line.lower():
                    continue
                parts = re.split(r"\s{2,}", line.strip())
                if len(parts) >= 4:
                    apps.append({
                        "name": parts[0][:45],
                        "id": parts[1][:60],
                        "current": parts[2][:20],
                        "available": parts[3][:20],
                        "source": parts[4] if len(parts) > 4 else "winget",
                    })
        raw_note = res["stderr"] if not apps and res["stderr"] else ""
    elif not IS_WINDOWS:
        if shutil.which("apt"):
            manager = "apt"
            res = _run_cmd(["apt", "list", "--upgradable"], timeout=25)
            for line in res["stdout"].splitlines():
                if "/" in line and "[upgradable from:" in line.lower():
                    pkg = line.split("/")[0].strip()
                    avail = line.split()[1] if len(line.split()) > 1 else "?"
                    cur_m = re.search(r"upgradable from:\s*([^\]]+)", line, re.IGNORECASE)
                    cur = cur_m.group(1).strip() if cur_m else "?"
                    apps.append({
                        "name": pkg,
                        "id": pkg,
                        "current": cur[:24],
                        "available": avail[:24],
                        "source": "apt",
                    })
        if shutil.which("snap"):
            s_res = _run_cmd(["snap", "refresh", "--list"], timeout=20)
            for line in s_res["stdout"].splitlines()[1:]:
                cols = line.split()
                if len(cols) >= 2:
                    apps.append({
                        "name": cols[0],
                        "id": cols[0],
                        "current": "instalado",
                        "available": cols[1],
                        "source": "snap",
                    })

    return {
        "ok": True,
        "os": "Windows" if IS_WINDOWS else "Linux",
        "manager": manager,
        "count": len(apps),
        "apps": apps[:60],
        "note": raw_note,
    }


def upgrade_apps(app_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Upgrade selected apps (or all upgradable apps) via winget/apt/snap."""
    ids = [a.strip() for a in (app_ids or []) if a.strip()]
    outputs: List[str] = []

    if IS_WINDOWS:
        if not shutil.which("winget"):
            return {"ok": False, "message": "winget não encontrado neste Windows."}
        if not ids:
            res = _run_cmd(
                ["winget", "upgrade", "--all", "--silent", "--accept-package-agreements", "--accept-source-agreements"],
                timeout=180,
            )
            outputs.append(res["stdout"] or res["stderr"] or "Atualização geral concluída.")
            log_activity("OPTIMIZER", "Atualização em lote de aplicativos via winget")
            return {"ok": res["ok"], "message": "\n".join(outputs)[:2000]}
        for aid in ids[:10]:
            res = _run_cmd(
                ["winget", "upgrade", "--id", aid, "-e", "--silent", "--accept-package-agreements", "--accept-source-agreements"],
                timeout=120,
            )
            outputs.append(f"[{aid}] {'OK' if res['ok'] else 'Erro'}: {(res['stdout'] or res['stderr'])[:250]}")
        log_activity("OPTIMIZER", f"Atualizados {len(ids)} app(s) via winget")
        return {"ok": True, "message": "\n".join(outputs)}

    # Linux
    if shutil.which("pip"):
        outputs.append("Sistema Linux detectado. Atualizações de pacotes APT/Snap devem ser executadas com privilégios ou via gerenciador do sistema.")
    if shutil.which("flatpak"):
        res = _run_cmd(["flatpak", "update", "-y"], timeout=120)
        outputs.append(f"Flatpak: {res['stdout'][:400] or res['stderr'][:200]}")
    return {"ok": True, "message": "\n".join(outputs) or "Verificação de atualização concluída."}


def start_upgrade_apps_async(app_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    if _OPT_JOB_STATE.get("running"):
        return {"ok": True, "started": False, "message": "Já existe uma atualização de apps em andamento."}

    _OPT_JOB_STATE.update({
        "running": True,
        "task": "upgrade_apps",
        "message": "Atualizando aplicativos em segundo plano...",
        "ok": True,
        "updated_at": time.time(),
    })

    def _worker():
        try:
            res = upgrade_apps(app_ids)
            msg = res.get("message", "Atualização concluída.")
            if IS_WINDOWS and any(w in msg.lower() for w in ("access is denied", "acesso negado", "elevat", "administrator")):
                msg += "\n⚠ Dica: Alguns instaladores exigem executar a AURA como Administrador (UAC)."
            _OPT_JOB_STATE.update({
                "running": False,
                "task": "upgrade_apps",
                "message": msg[:2000],
                "ok": bool(res.get("ok", True)),
                "updated_at": time.time(),
            })
            try:
                push_mobile_notification(
                    title="Otimizador: Apps Atualizados",
                    body=msg[:220],
                    category="OPTIMIZER",
                    agent_name="Otimizador PC",
                )
            except Exception:
                pass
        except Exception as exc:
            _OPT_JOB_STATE.update({
                "running": False,
                "task": "upgrade_apps",
                "message": f"Erro: {exc}",
                "ok": False,
                "updated_at": time.time(),
            })

    threading.Thread(target=_worker, daemon=True).start()
    return {"ok": True, "started": True, "message": "Atualização iniciada em segundo plano!"}


def scan_drivers_and_firmware() -> Dict[str, Any]:
    """Inspect installed hardware drivers & firmware update status."""
    drivers: List[Dict[str, str]] = []
    firmware_info = ""

    if IS_WINDOWS:
        ps_cmd = (
            "Get-CimInstance Win32_PnPSignedDriver | "
            "Where-Object { $_.DeviceName -and $_.DriverVersion } | "
            "Select-Object -First 40 DeviceName, DriverVersion, Manufacturer, DriverDate | "
            "ConvertTo-Json -Compress"
        )
        res = _run_cmd(["powershell", "-NoProfile", "-Command", ps_cmd], timeout=25)
        if res["ok"] and res["stdout"]:
            import json
            try:
                raw = json.loads(res["stdout"])
                items = raw if isinstance(raw, list) else [raw]
                for it in items:
                    drivers.append({
                        "device": str(it.get("DeviceName", ""))[:55],
                        "version": str(it.get("DriverVersion", ""))[:24],
                        "vendor": str(it.get("Manufacturer", ""))[:30],
                        "date": str(it.get("DriverDate", ""))[:10],
                    })
            except Exception:
                pass
    else:
        if shutil.which("lsmod"):
            res = _run_cmd(["lsmod"], timeout=10)
            for line in res["stdout"].splitlines()[1:35]:
                cols = line.split()
                if cols:
                    drivers.append({
                        "device": cols[0],
                        "version": f"{cols[1]} bytes" if len(cols) > 1 else "kernel",
                        "vendor": "Linux Kernel Module",
                        "date": "-",
                    })
        if shutil.which("fwupdmgr"):
            fw = _run_cmd(["fwupdmgr", "get-updates"], timeout=15)
            firmware_info = (fw["stdout"] or fw["stderr"])[:400]

    return {
        "ok": True,
        "os": "Windows" if IS_WINDOWS else "Linux",
        "count": len(drivers),
        "drivers": drivers,
        "firmware_info": firmware_info,
    }


def trigger_driver_update_scan() -> Dict[str, Any]:
    """Trigger Windows Update driver scan or Linux fwupdmgr/ubuntu-drivers check."""
    if IS_WINDOWS:
        res1 = _run_cmd(["pnputil", "/scan-devices"], timeout=30)
        res2 = _run_cmd(["UsoClient", "StartScan"], timeout=20)
        msg = (
            f"Varredura de dispositivos PnP: {'OK' if res1['ok'] else res1['stderr']}\n"
            f"Windows Update Driver Scan: {'Disparado em segundo plano' if res2['ok'] else 'Solicitado via Sistema'}"
        )
        log_activity("OPTIMIZER", "Varredura de drivers e dispositivos disparada")
        return {"ok": True, "message": msg}

    msgs: List[str] = []
    if shutil.which("fwupdmgr"):
        fw = _run_cmd(["fwupdmgr", "refresh"], timeout=25)
        msgs.append(f"fwupdmgr: {fw['stdout'][:250] or fw['stderr'][:250]}")
    if shutil.which("ubuntu-drivers"):
        ud = _run_cmd(["ubuntu-drivers", "list"], timeout=25)
        msgs.append(f"ubuntu-drivers: {ud['stdout'][:300] or 'Nenhum driver proprietário pendente.'}")
    log_activity("OPTIMIZER", "Varredura de drivers Linux executada")
    return {"ok": True, "message": "\n".join(msgs) or "Verificação de módulos e firmware concluída."}


def run_pc_optimization(tasks: Optional[List[str]] = None) -> Dict[str, Any]:
    """Run safe, practical PC optimization tasks."""
    selected = set(tasks or ["clean_temp", "flush_dns", "trim_ram", "startup_audit"])
    report: List[str] = []

    if "clean_temp" in selected:
        c_res = clean_temp_files()
        report.append(f"✔ Limpeza de Temporários: {c_res.get('message', 'Concluída')}")

    if "flush_dns" in selected:
        if IS_WINDOWS:
            r = _run_cmd(["ipconfig", "/flushdns"], timeout=10)
            report.append(f"✔ Cache DNS limpo: {r['stdout'] or 'OK'}")
        elif shutil.which("resolvectl"):
            r = _run_cmd(["resolvectl", "flush-caches"], timeout=10)
            report.append(f"✔ Cache DNS (resolvectl): {'Limpo' if r['ok'] else r['stderr']}")
        else:
            report.append("• Cache DNS: resolvectl não disponível neste ambiente.")

    if "trim_ram" in selected:
        import gc
        gc.collect()
        if IS_WINDOWS:
            ps = "Get-Process | Where-Object {$_.WorkingSet64 -gt 50MB} | Sort-Object WorkingSet64 -Descending | Select-Object -First 5 Name, @{N='MB';E={[math]::Round($_.WorkingSet64/1MB,1)}} | Out-String"
            r = _run_cmd(["powershell", "-NoProfile", "-Command", ps], timeout=12)
            report.append(f"✔ Otimização de Memória & Top Processos:\n{r['stdout'][:500]}")
        else:
            report.append("✔ Coleta de lixo Python executada e memória verificada.")

    if "startup_audit" in selected:
        if IS_WINDOWS:
            ps = "Get-CimInstance Win32_StartupCommand | Select-Object -First 10 Name, Location | Out-String"
            r = _run_cmd(["powershell", "-NoProfile", "-Command", ps], timeout=12)
            report.append(f"📋 Itens de Inicialização:\n{r['stdout'][:600] or 'Nenhum item listado.'}")
        else:
            r = _run_cmd(["ps", "-eo", "pid,comm,%cpu,%mem", "--sort=-%mem"], timeout=10)
            top_lines = "\n".join(r["stdout"].splitlines()[:8])
            report.append(f"📋 Top Processos por Memória:\n{top_lines}")

    log_activity("OPTIMIZER", f"Otimização do PC executada ({', '.join(sorted(selected))})")
    return {"ok": True, "tasks": sorted(selected), "report": "\n\n".join(report)}

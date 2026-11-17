import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import storage  # noqa: E402
import free_ai_router  # noqa: E402
import terminal_manager  # noqa: E402
import system_optimizer  # noqa: E402
import system_tools  # noqa: E402


def test_chat_history_persistence():
    storage.init_db()
    storage.clear_chat_history()
    storage.append_chat_history("user", "Olá AURA")
    storage.append_chat_history("assistant", "Olá! Como posso ajudar?", provider="Test")
    items = storage.get_chat_history(10)
    assert len(items) == 2
    assert items[0]["role"] == "user"
    assert items[1]["provider"] == "Test"
    storage.clear_chat_history()


def test_settings_remote_pin_and_workspace():
    storage.init_db()
    s = storage.get_settings()
    assert "remote_pin" in s
    assert "active_workspace" in s
    assert "notify_on_tasks" in s


def test_free_ai_router_clean_and_routing():
    raw = "<think>raciocínio interno</think>\nResposta final limpa."
    assert free_ai_router._clean_model_reply(raw) == "Resposta final limpa."
    temp_plan, order_plan = free_ai_router._resolve_task_config("planning", None)
    assert temp_plan == 0.2
    assert order_plan[0] == "free:deepseek"
    temp_code, order_code = free_ai_router._resolve_task_config("coding", None)
    assert temp_code == 0.25
    assert order_code[0] == "free:qwen-coder"


def test_terminal_sync_cwd(tmp_path):
    sess = terminal_manager.get_or_init_terminal_session("test-node-sync")
    assert sess["node_id"] == "test-node-sync"
    res = terminal_manager.sync_all_terminal_cwds(str(tmp_path))
    assert res["ok"] is True
    assert terminal_manager.get_or_init_terminal_session("test-node-sync")["cwd"] == str(tmp_path.resolve())


def test_system_optimizer_smoke():
    opt = system_optimizer.run_pc_optimization(["trim_ram"])
    assert opt["ok"] is True
    assert "report" in opt
    drv = system_optimizer.scan_drivers_and_firmware()
    assert drv["ok"] is True
    apps = system_optimizer.scan_updatable_apps()
    assert apps["ok"] is True
    st = system_optimizer.get_optimizer_job_status()
    assert "running" in st


def test_process_manager_smoke():
    procs = system_tools.get_top_processes(limit=10, sort_by="ram")
    assert isinstance(procs, list)
    assert len(procs) >= 1
    assert {"pid", "name", "cpu_percent", "memory_mb"} <= set(procs[0].keys())
    blocked = system_tools.kill_process_by_pid(-1)
    assert blocked["success"] is False


def test_api_endpoints_and_pin_guard():
    import httpx
    import app as aura_app

    async def _run():
        transport = httpx.ASGITransport(app=aura_app.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            r_hist = await client.get("/api/chat/history")
            assert r_hist.status_code == 200
            assert "items" in r_hist.json()

            r_stats = await client.get("/api/system/stats")
            assert r_stats.status_code == 200
            assert "cpu" in r_stats.json() and "ram" in r_stats.json()

            r_procs = await client.get("/api/system/processes?limit=10&sort=ram")
            assert r_procs.status_code == 200
            assert len(r_procs.json()["processes"]) >= 1

            r_ws = await client.get("/api/workspace/projects")
            assert r_ws.status_code == 200
            assert "projects" in r_ws.json()

            r_opt = await client.post("/api/optimizer/run", json={"tasks": ["trim_ram"]})
            assert r_opt.status_code == 200
            assert r_opt.json()["ok"] is True

            r_opt_st = await client.get("/api/optimizer/status")
            assert r_opt_st.status_code == 200
            assert "running" in r_opt_st.json()

        # Test remote PIN guard with non-local client IP
        orig_pin = storage.get_settings().get("remote_pin", "")
        try:
            storage.update_settings({"remote_pin": "4321"})
            remote_transport = httpx.ASGITransport(app=aura_app.app, client=("192.168.1.99", 50000))
            async with httpx.AsyncClient(transport=remote_transport, base_url="http://testserver") as remote_client:
                r_denied = await remote_client.get("/api/workspace/projects")
                assert r_denied.status_code == 401
                r_ok = await remote_client.get("/api/workspace/projects", headers={"X-AURA-Pin": "4321"})
                assert r_ok.status_code == 200
        finally:
            storage.update_settings({"remote_pin": orig_pin})

    asyncio.run(_run())


def test_packs_dev_utils_and_toggle():
    import packs_manager

    storage.init_db()
    packs = packs_manager.list_packs()
    assert len(packs) >= 6
    pack_ids = {p["id"] for p in packs}
    assert {"weather", "finance", "news", "translate", "dev_utils", "productivity"} <= pack_ids

    pwd = packs_manager.run_dev_util("password", {"length": 20})
    assert pwd["ok"] is True and len(pwd["result"]) == 20

    uid = packs_manager.run_dev_util("uuid")
    assert uid["ok"] is True and len(uid["result"]) == 36

    h = packs_manager.run_dev_util("hash", {"text": "aura", "algo": "sha256"})
    assert h["ok"] is True and len(h["result"]) == 64

    b64 = packs_manager.run_dev_util("base64_encode", {"text": "aura-os"})
    assert b64["ok"] is True
    b64_dec = packs_manager.run_dev_util("base64_decode", {"text": b64["result"]})
    assert b64_dec["result"] == "aura-os"

    calc = packs_manager.safe_calculate("(10 + 5) * 3 - 5")
    assert calc["ok"] is True and calc["result"] == 40

    bad_calc = packs_manager.safe_calculate("__import__('os').system('echo 1')")
    assert bad_calc["ok"] is False

    # Toggle pack off and back on
    try:
        t_off = packs_manager.toggle_pack("dev_utils", enabled=False)
        assert t_off["ok"] is True and t_off["enabled"] is False
        blocked = packs_manager.run_pack_action("dev_utils", "uuid")
        assert blocked["ok"] is False
    finally:
        packs_manager.toggle_pack("dev_utils", enabled=True)


def test_extended_system_and_api_endpoints():
    import httpx
    import app as aura_app

    ports = system_tools.get_open_ports(limit=10)
    assert isinstance(ports, list)

    dev_env = system_tools.get_dev_environment_info()
    assert dev_env["ok"] is True
    assert "python" in dev_env["tools"]

    pool_ids = {p["id"] for p in free_ai_router.get_free_pool_status()}
    assert {"cerebras:llama-3.3-70b", "deepseek:chat", "custom:openai"} <= pool_ids

    backup = storage.export_all_data()
    assert "tasks" in backup and "settings" in backup

    async def _run():
        transport = httpx.ASGITransport(app=aura_app.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            r_cap = await client.get("/api/capabilities")
            assert r_cap.status_code == 200
            assert "packs" in r_cap.json()

            r_packs = await client.get("/api/packs")
            assert r_packs.status_code == 200
            assert len(r_packs.json()["packs"]) >= 6

            r_du = await client.post("/api/packs/dev-utils", json={"action": "calc", "params": {"expression": "21 * 2"}})
            assert r_du.status_code == 200
            assert r_du.json()["result"] == 42

            r_ports = await client.get("/api/system/ports?limit=10")
            assert r_ports.status_code == 200
            assert "ports" in r_ports.json()

            r_env = await client.get("/api/system/dev-env")
            assert r_env.status_code == 200
            assert r_env.json()["ok"] is True

            r_bkp = await client.get("/api/system/backup")
            assert r_bkp.status_code == 200
            assert "exported_at" in r_bkp.json()

            r_wh = await client.post("/api/webhooks/trigger", json={"event": "pack", "payload": {"pack_id": "dev_utils", "action": "uuid"}})
            assert r_wh.status_code == 200
            assert r_wh.json()["ok"] is True
            assert len(r_wh.json()["result"]["result"]) == 36

    asyncio.run(_run())

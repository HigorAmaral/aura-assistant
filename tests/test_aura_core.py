import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import storage  # noqa: E402
import free_ai_router  # noqa: E402
import terminal_manager  # noqa: E402
import maestri_orchestrator  # noqa: E402
import system_optimizer  # noqa: E402


def test_coding_squad_template_exists():
    tpls = storage.get_maestri_templates()
    assert "coding_squad" in tpls
    squad = tpls["coding_squad"]
    node_ids = {n["id"] for n in squad["nodes"]}
    assert {"squad-maestro", "squad-db", "squad-backend", "squad-frontend", "squad-qa"} <= node_ids
    assert len(squad["edges"]) >= 5


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


def test_maestro_cancel_state():
    res = maestri_orchestrator.cancel_maestro_run()
    assert res["ok"] is True
    st = maestri_orchestrator.get_maestro_live_status()
    assert st["phase"] == "cancelling"


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


def test_api_endpoints_and_pin_guard():
    import asyncio
    import httpx
    import app as aura_app

    async def _run():
        transport = httpx.ASGITransport(app=aura_app.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            r_hist = await client.get("/api/chat/history")
            assert r_hist.status_code == 200
            assert "items" in r_hist.json()

            r_ws = await client.get("/api/workspace/projects")
            assert r_ws.status_code == 200
            assert "projects" in r_ws.json()

            r_m_st = await client.get("/api/canvas/maestro-status")
            assert r_m_st.status_code == 200
            assert "phase" in r_m_st.json()

            r_m_cancel = await client.post("/api/canvas/maestro-cancel")
            assert r_m_cancel.status_code == 200
            assert r_m_cancel.json()["ok"] is True

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


def test_official_maestro_features():
    import asyncio
    import httpx
    import app as aura_app

    async def _run():
        transport = httpx.ASGITransport(app=aura_app.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            r_pb = await client.get("/api/maestri/playbooks")
            assert r_pb.status_code == 200
            assert len(r_pb.json().get("playbooks", [])) >= 1

            r_ar = await client.get("/api/maestri/autorun/status")
            assert r_ar.status_code == 200
            assert "running" in r_ar.json()

            r_wt = await client.get("/api/maestri/worktrees")
            assert r_wt.status_code == 200
            assert r_wt.json()["ok"] is True

            r_files = await client.get("/api/workspace/files?limit=20")
            assert r_files.status_code == 200
            assert len(r_files.json().get("files", [])) >= 1

            r_log = await client.get("/api/workspace/log?limit=5")
            assert r_log.status_code == 200
            assert r_log.json()["ok"] is True

    asyncio.run(_run())



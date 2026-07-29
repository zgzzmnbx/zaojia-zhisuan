import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "backend" / "feishu_bot_supervisor.py"


def load_supervisor_module():
    spec = importlib.util.spec_from_file_location("feishu_bot_supervisor", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_reconcile_enabled_profiles_delegates_to_shared_starter(monkeypatch):
    module = load_supervisor_module()
    expected = {"default": True, "weact_cost": False}
    monkeypatch.setattr(module, "start_enabled_bot_processes", lambda: expected)

    assert module.reconcile_enabled_profiles() == expected

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.feishu_app_bot import (  # noqa: E402
    append_runtime_event,
    bot_pid_path,
    bot_process_running,
    credential_profiles,
    start_enabled_bot_processes,
)


POLL_SECONDS = 2.0
STOP_TIMEOUT_SECONDS = 8.0


def _read_pid(profile_id: str) -> int | None:
    try:
        return int(bot_pid_path(profile_id).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def stop_profile_process(profile_id: str, timeout_seconds: float = STOP_TIMEOUT_SECONDS) -> None:
    pid = _read_pid(profile_id)
    if not pid:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        bot_pid_path(profile_id).unlink(missing_ok=True)
        return
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    while bot_process_running(profile_id) and time.monotonic() < deadline:
        time.sleep(0.1)
    if bot_process_running(profile_id):
        try:
            os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
        except OSError:
            pass
    bot_pid_path(profile_id).unlink(missing_ok=True)


def reconcile_enabled_profiles() -> dict[str, bool]:
    """Start every enabled platform once; disabled runners exit through their own control loop."""
    return start_enabled_bot_processes()


def main() -> int:
    stop_event = threading.Event()

    def request_stop(_signum=None, _frame=None) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    append_runtime_event("process", "双平台长连接监督器已启动")
    try:
        while not stop_event.is_set():
            try:
                reconcile_enabled_profiles()
            except Exception as exc:  # noqa: BLE001 - supervisor must remain alive and retry
                append_runtime_event(
                    "process",
                    f"双平台长连接监督器本轮检查失败：{exc}",
                    level="error",
                )
            stop_event.wait(POLL_SECONDS)
    finally:
        for profile in credential_profiles():
            profile_id = str(profile.get("profile_id") or "").strip()
            if profile_id and bot_process_running(profile_id):
                stop_profile_process(profile_id)
        append_runtime_event("process", "双平台长连接监督器已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

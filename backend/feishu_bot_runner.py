from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.feishu_app_bot import (
    DB_PATH, FeishuApi, IgnoreEvent, ProfessionalApi, TaskStore, TaskWorker, accept_event,
    accept_knowledge_event, answer_knowledge_event,
    CONTROL_PATH, PID_PATH, cleanup_expired, is_bot_enabled, load_bot_defaults, load_credentials,
)


def main() -> int:
    defaults = load_bot_defaults()
    credentials = load_credentials()
    if not is_bot_enabled():
        print("第二层飞书机器人未启用。")
        return 0
    if not credentials.get("app_id") or not credentials.get("app_secret"):
        print("第二层飞书机器人未配置本机应用凭证。")
        return 0
    try:
        import lark_oapi as lark
    except ImportError:
        print("缺少 lark-oapi，请先安装 backend/requirements.txt。")
        return 2

    store = TaskStore(DB_PATH)
    store.recover_interrupted()
    cleanup_expired(store)
    feishu = FeishuApi(credentials["app_id"], credentials["app_secret"])
    professional = ProfessionalApi(str(defaults.get("apiBaseUrl") or "http://127.0.0.1:8000"))
    worker = TaskWorker(store, feishu, professional)
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")

    def control_loop() -> None:
        while True:
            time.sleep(1)
            if not is_bot_enabled():
                PID_PATH.unlink(missing_ok=True)
                os._exit(0)

    def worker_loop() -> None:
        while True:
            if not worker.run_once():
                time.sleep(1)

    threading.Thread(target=worker_loop, name="feishu-task-worker", daemon=True).start()
    threading.Thread(target=control_loop, name="feishu-control", daemon=True).start()

    def handle_message(data):
        try:
            knowledge = accept_knowledge_event(data, store, feishu)
            if knowledge is not None:
                if not knowledge.get("duplicate"):
                    threading.Thread(
                        target=answer_knowledge_event,
                        args=(knowledge["chat_id"], knowledge["question"], feishu, professional),
                        name="feishu-knowledge-query",
                        daemon=True,
                    ).start()
                return
            accept_event(data, store, feishu)
        except IgnoreEvent:
            return
        except ValueError as exc:
            raw = data.to_dict() if hasattr(data, "to_dict") else {}
            chat_id = (((raw.get("event") or {}).get("message") or {}).get("chat_id") or "")
            if chat_id:
                feishu.send_text(chat_id, str(exc))

    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(handle_message)
        .build()
    )
    client = lark.ws.Client(
        credentials["app_id"], credentials["app_secret"],
        event_handler=handler,
        log_level=lark.LogLevel.WARNING,
    )
    print("第二层飞书机器人长连接已启动。")
    client.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

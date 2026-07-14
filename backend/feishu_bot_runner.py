from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.feishu_app_bot import (
    DB_PATH, FeishuApi, IgnoreEvent, ProfessionalApi, TaskStore, TaskWorker, accept_event,
    accept_knowledge_event, acknowledge_message_event, answer_knowledge_event, append_runtime_event, describe_message_event,
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
    recovered = store.recover_interrupted()
    cleanup_expired(store)
    domain = credentials.get("domain") or "https://open.feishu.cn"
    profile_id = str(credentials.get("profile_id") or "")
    append_runtime_event(
        "process",
        f"机器人进程已就绪，准备连接 {domain}",
        profile_id=profile_id,
    )
    if recovered:
        append_runtime_event("task", f"发现 {recovered} 个中断任务，已进入恢复队列", level="warning", profile_id=profile_id)
    feishu = FeishuApi(credentials["app_id"], credentials["app_secret"], domain=domain)
    professional = ProfessionalApi(str(defaults.get("apiBaseUrl") or "http://127.0.0.1:8000"))
    worker = TaskWorker(store, feishu, professional)
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")

    def control_loop() -> None:
        while True:
            time.sleep(1)
            if not is_bot_enabled():
                append_runtime_event("process", "机器人接收已关闭，长连接进程正在退出", profile_id=profile_id)
                PID_PATH.unlink(missing_ok=True)
                os._exit(0)

    def worker_loop() -> None:
        while True:
            if not worker.run_once():
                time.sleep(1)

    threading.Thread(target=worker_loop, name="feishu-task-worker", daemon=True).start()
    threading.Thread(target=control_loop, name="feishu-control", daemon=True).start()

    reaction_lock = threading.Lock()
    reaction_message_ids: OrderedDict[str, None] = OrderedDict()

    def acknowledge_in_background(data) -> None:
        try:
            acknowledge_message_event(data, feishu)
            append_runtime_event(
                "message",
                "已向收到的消息添加“了解”表情回应",
                level="success",
                profile_id=profile_id,
            )
        except Exception as exc:
            append_runtime_event(
                "message",
                f"添加“了解”表情回应失败：{exc}",
                level="warning",
                profile_id=profile_id,
            )
            try:
                raw = data.to_dict() if hasattr(data, "to_dict") else data
                message_id = str((((raw.get("event") or {}).get("message") or {}).get("message_id") or ""))
            except (AttributeError, TypeError):
                message_id = ""
            if message_id:
                with reaction_lock:
                    reaction_message_ids.pop(message_id, None)

    def schedule_acknowledgement(data) -> None:
        try:
            raw = data.to_dict() if hasattr(data, "to_dict") else data
            message_id = str((((raw.get("event") or {}).get("message") or {}).get("message_id") or "")).strip()
        except (AttributeError, TypeError):
            return
        if not message_id:
            return
        with reaction_lock:
            if message_id in reaction_message_ids:
                return
            reaction_message_ids[message_id] = None
            while len(reaction_message_ids) > 2000:
                reaction_message_ids.popitem(last=False)
        threading.Thread(
            target=acknowledge_in_background,
            args=(data,),
            name="feishu-message-reaction",
            daemon=True,
        ).start()

    def handle_message(data):
        message_context = ""
        schedule_acknowledgement(data)

        def event_context() -> str:
            nonlocal message_context
            if not message_context:
                message_context = describe_message_event(data, feishu)
            return message_context

        try:
            knowledge = accept_knowledge_event(data, store, feishu)
            if knowledge is not None:
                append_runtime_event(
                    "knowledge",
                    (
                        "收到知识库问题，已进入查询"
                        if not knowledge.get("duplicate")
                        else "收到重复知识库事件，已忽略重复处理"
                    ) + f"｜{event_context()}",
                    profile_id=profile_id,
                )
                if not knowledge.get("duplicate"):
                    threading.Thread(
                        target=answer_knowledge_event,
                        args=(knowledge["chat_id"], knowledge["question"], feishu, professional),
                        name="feishu-knowledge-query",
                        daemon=True,
                    ).start()
                return
            result = accept_event(data, store, feishu)
            if result.get("task_id"):
                append_runtime_event(
                    "message",
                    (
                        "收到 Excel 文件消息，任务已进入顺序队列"
                        if result.get("created")
                        else "收到重复文件事件，未重复创建任务"
                    ) + f"｜{event_context()}",
                    level="success" if result.get("created") else "warning",
                    task_id=str(result.get("task_id") or ""),
                    profile_id=profile_id,
                )
            elif result.get("pending"):
                append_runtime_event(
                    "message",
                    f"收到收件指令，已开启 5 分钟文件接收窗口｜{event_context()}",
                    profile_id=profile_id,
                )
        except IgnoreEvent:
            return
        except ValueError as exc:
            append_runtime_event(
                "message",
                f"收到消息但未通过任务校验：{exc}｜{event_context()}",
                level="warning",
                profile_id=profile_id,
            )
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
        log_level=lark.LogLevel.INFO,
        domain=domain,
        auto_reconnect=True,
    )
    append_runtime_event("connection", f"正在建立长连接：{domain}", profile_id=profile_id)
    print(f"第二层飞书机器人正在建立长连接：{domain}", flush=True)
    client.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

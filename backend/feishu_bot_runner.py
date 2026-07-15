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
    accept_conversation_event, accept_knowledge_event, acknowledge_message_event, answer_chat_event, answer_group_members_event,
    answer_task_result_event,
    answer_knowledge_event, append_runtime_event, describe_message_event,
    CONTROL_PATH, PID_PATH, cleanup_expired, credential_configuration_issue, is_bot_enabled, load_bot_defaults, load_credentials,
    message_is_stale, parse_message_envelope, should_acknowledge_message, utc_now,
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
    configuration_issue = credential_configuration_issue(credentials=credentials)
    if configuration_issue:
        append_runtime_event(
            "config",
            configuration_issue,
            level="error",
            profile_id=str(credentials.get("profile_id") or ""),
        )
        print(configuration_issue)
        return 3
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
    professional = ProfessionalApi(str(defaults.get("apiBaseUrl") or "http://127.0.0.1:8000"))
    try:
        professional.health_check()
    except Exception as exc:
        append_runtime_event(
            "connection",
            f"专业服务连接失败，机器人未启动业务接收：{professional.base_url}（{exc}）",
            level="error",
            profile_id=profile_id,
        )
        print(f"专业服务连接失败：{professional.base_url}（{exc}）")
        return 4
    feishu = FeishuApi(credentials["app_id"], credentials["app_secret"], domain=domain)
    bot_open_id = ""
    bot_name = ""
    for attempt in range(3):
        try:
            bot_open_id, bot_name = feishu.resolve_bot_identity()
            break
        except Exception as exc:
            if attempt == 2:
                append_runtime_event(
                    "connection",
                    f"无法确认当前机器人身份，群聊消息将保持静默：{exc}",
                    level="error",
                    profile_id=profile_id,
                )
            else:
                time.sleep(attempt + 1)
    if bot_open_id or bot_name:
        append_runtime_event(
            "connection",
            f"当前机器人身份已确认：{bot_name or '未命名机器人'}",
            level="success",
            profile_id=profile_id,
        )
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

    def acknowledge_in_background(data, message_id: str) -> None:
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
            with reaction_lock:
                reaction_message_ids.pop(message_id, None)

    def schedule_acknowledgement(data, *, received_at: str) -> None:
        try:
            envelope = parse_message_envelope(data)
        except ValueError:
            return
        if not should_acknowledge_message(
            data,
            bot_open_id=bot_open_id,
            bot_name=bot_name,
            received_at=received_at,
        ):
            return
        message_id = envelope.message_id
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
            args=(data, message_id),
            name="feishu-message-reaction",
            daemon=True,
        ).start()

    def handle_message(data):
        message_context = ""
        received_at = utc_now()

        def event_context() -> str:
            nonlocal message_context
            if not message_context:
                message_context = describe_message_event(data, feishu, received_at=received_at)
            return message_context

        try:
            envelope = parse_message_envelope(data)
            accepted, duplicate_key = store.record_inbound_message(
                event_id=envelope.event_id,
                message_id=envelope.message_id,
                message_created_at=envelope.message_created_at,
                received_at=received_at,
            )
            if not accepted:
                reason = {
                    "event_id": "事件 ID",
                    "message_id": "消息 ID",
                    "missing_id": "消息标识",
                }.get(duplicate_key, "持久去重记录")
                append_runtime_event(
                    "message",
                    f"重复消息已静默拦截（{reason}命中）｜{event_context()}",
                    level="warning",
                    profile_id=profile_id,
                )
                return
            if message_is_stale(envelope, received_at=received_at):
                append_runtime_event(
                    "message",
                    "过期消息已静默拦截（平台创建时间超过 5 分钟）｜" + event_context(),
                    level="warning",
                    profile_id=profile_id,
                )
                return
            schedule_acknowledgement(data, received_at=received_at)
            knowledge = accept_knowledge_event(
                data, store, feishu, bot_open_id=bot_open_id, bot_name=bot_name,
            )
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
            result = accept_event(
                data, store, feishu, bot_open_id=bot_open_id, bot_name=bot_name,
            )
            if result and result.get("task_id"):
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
            elif result and result.get("pending"):
                append_runtime_event(
                    "message",
                    f"收到收件指令，已开启 1 分钟文件接收窗口｜{event_context()}",
                    profile_id=profile_id,
                )
            else:
                conversation = accept_conversation_event(
                    data, store, feishu, bot_open_id=bot_open_id, bot_name=bot_name,
                )
                conversation_log = {
                    "greeting": "收到问候，已回复自我介绍和使用说明",
                    "members": "收到群成员确定性查询指令，已调用群成员接口",
                    "members_private": "收到单聊群成员查询指令，已提示转到目标群聊",
                    "help": "收到帮助指令，已回复确定性指令清单",
                    "task_list": "收到任务列表指令，已返回当前会话最近任务",
                    "progress": "收到任务进度指令，已返回当前会话任务状态",
                    "risk": "收到任务风险指令，已返回当前会话风险统计",
                    "high_risk": "收到高风险指令，已返回当前会话高风险任务",
                    "result": "收到成果重发指令，已进入后台回传",
                    "result_unavailable": "收到成果重发指令，但任务尚未完成",
                    "task_usage": "收到不完整任务指令，已提示标准格式",
                    "task_missing": "收到任务查询指令，但当前会话未找到该任务",
                }.get(conversation.get("kind"), "收到普通问题，已进入大模型托底问答")
                append_runtime_event(
                    "message",
                    conversation_log + f"｜{event_context()}",
                    level="warning" if conversation.get("duplicate") else "info",
                    profile_id=profile_id,
                )
                if conversation.get("kind") == "chat" and not conversation.get("duplicate"):
                    threading.Thread(
                        target=answer_chat_event,
                        args=(conversation["chat_id"], conversation["question"], feishu, professional),
                        name="feishu-llm-chat",
                        daemon=True,
                    ).start()
                elif conversation.get("kind") == "members" and not conversation.get("duplicate"):
                    threading.Thread(
                        target=answer_group_members_event,
                        args=(conversation["chat_id"], feishu),
                        name="feishu-group-members",
                        daemon=True,
                    ).start()
                elif conversation.get("kind") == "result" and not conversation.get("duplicate"):
                    threading.Thread(
                        target=answer_task_result_event,
                        args=(conversation["chat_id"], conversation["task_id"], store, feishu),
                        name="feishu-task-result",
                        daemon=True,
                    ).start()
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

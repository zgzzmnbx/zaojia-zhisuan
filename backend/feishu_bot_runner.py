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
    CONTROL_PATH, PID_PATH, cleanup_expired, credential_configuration_issue, is_bot_enabled, load_bot_defaults, load_completion_card_app_url, load_credentials,
    delayed_file_matches_pending_window, message_is_stale, parse_message_envelope,
    should_acknowledge_message, utc_now,
)
from app import external_task_dispatch


def deliver_external_review_bundle(
    task_id: str,
    *,
    profile_id: str,
    feishu: FeishuApi,
) -> dict:
    dispatch_store = external_task_dispatch.ExternalDispatchStore()
    task = dispatch_store.get_task(task_id)
    if not task:
        raise external_task_dispatch.DispatchValidationError("未找到外部派发任务", status_code=404)
    result_path = Path(str(task.get("submission_excel_path") or ""))
    if not result_path.is_file():
        raise external_task_dispatch.DispatchValidationError("编制成果文件不存在，无法发起复核", status_code=409)
    try:
        file_message_ids: list[str] = []
        card_message_ids: list[str] = []
        targets = external_task_dispatch.review_delivery_targets(task)
        external_task_dispatch.enforce_outbound_audience_safety(
            feishu,
            targets,
            named_recipients={
                str(item.get("platform_user_id") or "").strip(): str(item.get("display_name") or "").strip()
                for item in task.get("_reviewers") or []
            },
        )
        for receive_id, receive_id_type in targets:
            file_message_ids.append(feishu.send_file_to(receive_id, receive_id_type, result_path))
            card_message_ids.append(
                feishu.send_card_to(
                    receive_id,
                    receive_id_type,
                    external_task_dispatch.build_external_review_card(task),
                )
            )
        dispatch_store.record_attempt(task_id, "review_file", "sent")
        dispatch_store.mark_submission_delivery(task_id, status="sent", message_ids=file_message_ids)
        dispatch_store.record_attempt(task_id, "review_card", "sent")
        task = dispatch_store.mark_review_card(
            task_id,
            status="sent",
            message_id=json.dumps([item for item in card_message_ids if item], ensure_ascii=False),
        )
        append_runtime_event(
            "task",
            f"外部任务 {task_id} 的编制成果和第 {task.get('review_round')} 轮复核卡已投递",
            level="success",
            task_id=task_id,
            profile_id=profile_id,
        )
        return task
    except Exception as exc:
        dispatch_store.record_attempt(task_id, "review_bundle", "failed", str(exc))
        dispatch_store.mark_submission_delivery(task_id, status="failed", error=exc)
        dispatch_store.rollback_review_submission(task_id, exc)
        raise


def deliver_external_completion_notification(
    task_id: str,
    *,
    profile_id: str,
    feishu: FeishuApi,
) -> None:
    dispatch_store = external_task_dispatch.ExternalDispatchStore()
    task = dispatch_store.get_task(task_id)
    if not task:
        return
    try:
        targets = external_task_dispatch.completion_delivery_targets(task)
        external_task_dispatch.enforce_outbound_audience_safety(
            feishu,
            targets,
            named_recipients={
                str(item.get("platform_user_id") or "").strip(): str(item.get("display_name") or "").strip()
                for item in [
                    {
                        "platform_user_id": task.get("assignee_user_id"),
                        "display_name": task.get("assignee_name"),
                    },
                    *(task.get("_reviewers") or []),
                ]
            },
        )
        message_ids = [
            feishu.send_card_to(
                receive_id,
                receive_id_type,
                external_task_dispatch.build_external_review_card(task),
            )
            for receive_id, receive_id_type in targets
        ]
        dispatch_store.record_attempt(task_id, "completion_card", "sent")
        dispatch_store.mark_completion_card(
            task_id,
            status="sent",
            message_id=json.dumps([item for item in message_ids if item], ensure_ascii=False),
        )
    except Exception as exc:
        dispatch_store.record_attempt(task_id, "completion_card", "failed", str(exc))
        dispatch_store.mark_completion_card(task_id, status="failed", error=str(exc))
        append_runtime_event(
            "task",
            f"外部任务 {task_id} 结论已保存，但完结通知发送失败：{external_task_dispatch.sanitize_dispatch_error(exc)}",
            level="warning",
            task_id=task_id,
            profile_id=profile_id,
        )


def process_external_submission_event(
    envelope,
    *,
    profile_id: str,
    feishu: FeishuApi,
) -> None:
    dispatch_store = external_task_dispatch.ExternalDispatchStore()
    is_private = envelope.chat_type in {"p2p", "private", "single"}
    task = dispatch_store.find_submission_window(
        operator_open_id=envelope.sender_id,
        platform_profile_id=profile_id,
        chat_id=envelope.chat_id,
        is_private=is_private,
        sent_at=envelope.message_created_at or utc_now(),
    )
    if not task or len(envelope.files) != 1:
        return
    file_key, file_name = envelope.files[0]
    target_path = dispatch_store.submission_target_path(task, file_name)
    try:
        feishu.download_file(envelope.message_id, file_key, target_path)
        dispatch_store.attach_submission(
            str(task["task_id"]),
            operator_open_id=envelope.sender_id,
            platform_profile_id=profile_id,
            message_id=envelope.message_id,
            file_name=file_name,
            file_path=target_path,
        )
        review_task, created = dispatch_store.submit_for_review(
            str(task["task_id"]),
            operator_open_id=envelope.sender_id,
            platform_profile_id=profile_id,
        )
        if created:
            deliver_external_review_bundle(str(task["task_id"]), profile_id=profile_id, feishu=feishu)
        feishu.send_text(
            envelope.chat_id,
            f"已收到任务 {task['task_id']} 的编制成果，已进入第 {review_task.get('review_round')} 轮多人复核。",
        )
    except Exception as exc:
        append_runtime_event(
            "task",
            f"外部任务 {task.get('task_id')} 编制成果接收或复核投递失败：{external_task_dispatch.sanitize_dispatch_error(exc)}",
            level="error",
            task_id=str(task.get("task_id") or ""),
            profile_id=profile_id,
        )
        try:
            feishu.send_text(
                envelope.chat_id,
                f"任务 {task.get('task_id')} 的编制成果提交失败：{external_task_dispatch.sanitize_dispatch_error(exc)}",
            )
        except Exception:
            pass


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
        from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse
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

    def schedule_acknowledgement(
        data,
        *,
        received_at: str,
        validated_pending_file: bool = False,
    ) -> None:
        try:
            envelope = parse_message_envelope(data)
        except ValueError:
            return
        if not should_acknowledge_message(
            data,
            bot_open_id=bot_open_id,
            bot_name=bot_name,
            received_at=received_at,
            validated_pending_file=validated_pending_file,
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
            dispatch_store = external_task_dispatch.ExternalDispatchStore()
            is_private = envelope.chat_type in {"p2p", "private", "single"}
            external_submission_task = None
            if len(envelope.files) == 1 and Path(envelope.files[0][1]).suffix.lower() == ".xlsx":
                external_submission_task = dispatch_store.find_submission_window(
                    operator_open_id=envelope.sender_id,
                    platform_profile_id=profile_id,
                    chat_id=envelope.chat_id,
                    is_private=is_private,
                    sent_at=envelope.message_created_at or received_at,
                )
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
            stale = message_is_stale(envelope, received_at=received_at)
            delayed_pending_file = stale and delayed_file_matches_pending_window(
                envelope,
                store,
                received_at=received_at,
            )
            delayed_external_submission = (
                stale
                and external_submission_task is not None
                and not message_is_stale(envelope, received_at=received_at, max_age_seconds=15 * 60)
            )
            if stale and not delayed_pending_file and not delayed_external_submission:
                append_runtime_event(
                    "message",
                    "过期消息已静默拦截（平台创建时间超过 5 分钟）｜" + event_context(),
                    level="warning",
                    profile_id=profile_id,
                )
                return
            if delayed_pending_file:
                append_runtime_event(
                    "message",
                    "平台延迟文件事件已通过原 1 分钟收件窗口校验｜" + event_context(),
                    level="warning",
                    profile_id=profile_id,
                )
            if delayed_external_submission:
                append_runtime_event(
                    "message",
                    "平台延迟的编制成果文件已通过原 1 分钟提交窗口校验｜" + event_context(),
                    level="warning",
                    task_id=str(external_submission_task.get("task_id") or ""),
                    profile_id=profile_id,
                )
            if external_submission_task is not None:
                schedule_acknowledgement(
                    data,
                    received_at=received_at,
                    validated_pending_file=True,
                )
                append_runtime_event(
                    "message",
                    "收到编制成果 Excel，正在绑定任务并投递多人复核｜" + event_context(),
                    task_id=str(external_submission_task.get("task_id") or ""),
                    profile_id=profile_id,
                )
                threading.Thread(
                    target=process_external_submission_event,
                    kwargs={"envelope": envelope, "profile_id": profile_id, "feishu": feishu},
                    name="feishu-external-review-submission",
                    daemon=True,
                ).start()
                return
            pending_file = bool(envelope.files) and store.matches_upload_window(
                envelope.chat_id,
                envelope.sender_id,
                envelope.message_created_at or received_at,
            )
            schedule_acknowledgement(
                data,
                received_at=received_at,
                validated_pending_file=pending_file,
            )
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

    def handle_card_action(data) -> P2CardActionTriggerResponse:
        event = getattr(data, "event", None)
        action = getattr(event, "action", None)
        operator = getattr(event, "operator", None)
        value = getattr(action, "value", None) or {}
        if not isinstance(value, dict) or value.get("action") not in {"claim_external_task", "submit_external_review", "review_external_task"}:
            return P2CardActionTriggerResponse({
                "toast": {"type": "warning", "content": "当前卡片操作暂不支持。"},
            })
        task_id = str(value.get("task_id") or "").strip()
        operator_open_id = str(getattr(operator, "open_id", "") or "").strip()
        action_name = str(value.get("action") or "")
        form_value = getattr(action, "form_value", None) or {}
        if hasattr(form_value, "to_dict"):
            form_value = form_value.to_dict()
        if not isinstance(form_value, dict):
            form_value = {}
        dispatch_store = external_task_dispatch.ExternalDispatchStore()
        try:
            if action_name == "submit_external_review":
                review_task, created = dispatch_store.open_submission_window(
                    task_id, operator_open_id=operator_open_id, platform_profile_id=profile_id,
                )
                append_runtime_event(
                    "task",
                    f"外部任务 {task_id} 已开启 1 分钟编制成果接收窗口",
                    task_id=task_id,
                    profile_id=profile_id,
                )
                return P2CardActionTriggerResponse({
                    "toast": {
                        "type": "success",
                        "content": "请在 1 分钟内发送编制完成的 .xlsx 文件。" if created else "正在等待您的 .xlsx 文件。",
                    },
                    "card": {"type": "raw", "data": external_task_dispatch.build_external_task_card(review_task, app_url=load_completion_card_app_url())},
                })
            if action_name == "review_external_task":
                decision = str(value.get("decision") or "")
                review_comment = str(form_value.get("review_comment") or value.get("review_comment") or "")
                reviewed_task, created = dispatch_store.review_task(
                    task_id,
                    operator_open_id=operator_open_id,
                    platform_profile_id=profile_id,
                    decision=decision,
                    comment=review_comment,
                )
                result_text = "复核通过" if decision == "approve" else "已退回编制"
                if created and str(reviewed_task.get("status") or "") in {"completed", "returned"}:
                    threading.Thread(
                        target=deliver_external_completion_notification,
                        kwargs={"task_id": task_id, "profile_id": profile_id, "feishu": feishu},
                        name="feishu-external-completion-delivery",
                        daemon=True,
                    ).start()
                append_runtime_event("task", f"外部任务 {task_id}：{result_text}", task_id=task_id, profile_id=profile_id)
                return P2CardActionTriggerResponse({
                    "toast": {"type": "success", "content": result_text if created else "本轮结论已记录。"},
                    "card": {"type": "raw", "data": external_task_dispatch.build_external_review_card(reviewed_task)},
                })
            claimed_task, created = dispatch_store.claim_task(task_id, operator_open_id=operator_open_id, platform_profile_id=profile_id)
            append_runtime_event(
                "task",
                f"外部任务 {task_id} {'已由目标编制人领取' if created else '重复领取已幂等返回'}",
                task_id=task_id,
                profile_id=profile_id,
            )
            return P2CardActionTriggerResponse({
                "toast": {"type": "success", "content": "领取成功，任务已进入您的待办。" if created else "您已领取过该任务。"},
                "card": {
                    "type": "raw",
                    "data": external_task_dispatch.build_external_task_card(
                        claimed_task,
                        app_url=load_completion_card_app_url(),
                    ),
                },
            })
        except external_task_dispatch.DispatchValidationError as exc:
            append_runtime_event(
                "task",
                f"外部任务卡片操作被拒绝：{task_id or '缺少任务编号'}（{exc}）",
                level="warning",
                task_id=task_id,
                profile_id=profile_id,
            )
            return P2CardActionTriggerResponse({
                "toast": {"type": "error", "content": str(exc)},
            })

    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(handle_message)
        .register_p2_card_action_trigger(handle_card_action)
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

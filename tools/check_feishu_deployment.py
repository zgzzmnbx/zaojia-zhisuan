from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = PROJECT_ROOT / "config" / "project-default-settings.json"
ENVIRONMENT_KEY = "FEISHU_APP_BOT_API_BASE_URL"
LOCAL_API_BASE_URL = "http://127.0.0.1:8000"
CLOUD_API_BASE_URL = "http://127.0.0.1:1285"
CLOUD_SERVICES = (
    "zaojiazhisuan.service",
    "zaojiazhisuan-feishu-bot.service",
)


def normalize_url(value: object) -> str:
    return str(value or "").strip().rstrip("/")


def read_project_default_api_base_url(path: Path = SETTINGS_PATH) -> str:
    raw = json.loads(path.read_text(encoding="utf-8"))
    section = raw.get("feishuAppBot") if isinstance(raw, dict) else None
    if not isinstance(section, dict):
        raise ValueError("项目默认配置缺少 feishuAppBot 分区")
    value = normalize_url(section.get("apiBaseUrl"))
    if not value:
        raise ValueError("项目默认配置缺少 feishuAppBot.apiBaseUrl")
    return value


def parse_environment_value(text: str, key: str = ENVIRONMENT_KEY) -> str:
    prefix = f"{key}="
    for item in text.split():
        candidate = item.strip().strip('"').strip("'")
        if candidate.startswith(prefix):
            return normalize_url(candidate[len(prefix):])
    return ""


def read_systemd_environment(service: str) -> str:
    result = subprocess.run(
        ["systemctl", "show", service, "--property=Environment", "--value"],
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_environment_value(result.stdout)


def read_systemd_state(service: str) -> str:
    result = subprocess.run(
        ["systemctl", "is-active", service],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def check_health(api_base_url: str) -> str:
    health_url = f"{normalize_url(api_base_url)}/api/health"
    try:
        with urlopen(health_url, timeout=10) as response:  # noqa: S310 - fixed local deployment URLs
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"健康检查失败：{health_url}（{exc}）") from exc
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise RuntimeError(f"健康检查未返回 status=ok：{health_url}")
    return str(payload.get("version") or "未知版本")


def read_bot_status(api_base_url: str) -> dict[str, object]:
    status_url = f"{normalize_url(api_base_url)}/api/collaboration/feishu-app-bot/status"
    try:
        with urlopen(status_url, timeout=10) as response:  # noqa: S310 - fixed local deployment URLs
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"机器人状态检查失败：{status_url}（{exc}）") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"机器人状态接口返回格式错误：{status_url}")
    return payload


def wait_for_bot_status(api_base_url: str, timeout_seconds: int = 30) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    latest: dict[str, object] = {}
    while True:
        latest = read_bot_status(api_base_url)
        if not latest.get("enabled") or latest.get("running"):
            return latest
        if time.monotonic() >= deadline:
            return latest
        time.sleep(1)


def validate_local(project_default: str, environment_value: str) -> list[str]:
    errors: list[str] = []
    if normalize_url(project_default) != LOCAL_API_BASE_URL:
        errors.append(f"本地项目默认地址必须为 {LOCAL_API_BASE_URL}，当前为 {project_default or '空'}")
    if environment_value and normalize_url(environment_value) != LOCAL_API_BASE_URL:
        errors.append(
            f"本机环境变量 {ENVIRONMENT_KEY} 不得指向云端端口，当前为 {environment_value}"
        )
    return errors


def validate_cloud(project_default: str, service_values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    if normalize_url(project_default) != LOCAL_API_BASE_URL:
        errors.append(
            f"共享项目默认值必须继续保持本机地址 {LOCAL_API_BASE_URL}，当前为 {project_default or '空'}"
        )
    for service in CLOUD_SERVICES:
        value = normalize_url(service_values.get(service))
        if value != CLOUD_API_BASE_URL:
            errors.append(
                f"{service} 必须显式设置 {ENVIRONMENT_KEY}={CLOUD_API_BASE_URL}，当前为 {value or '未设置'}"
            )
    return errors


def validate_cloud_runtime(service_states: dict[str, str], bot_status: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if service_states.get("zaojiazhisuan.service") != "active":
        errors.append(
            "zaojiazhisuan.service 当前状态不是 active："
            f"{service_states.get('zaojiazhisuan.service') or '未知'}"
        )
    if not bot_status.get("configured"):
        errors.append("第二层机器人凭证未配置")
    if not bot_status.get("profile_consistent"):
        errors.append("第二层机器人配置与项目登记不一致")
    if bot_status.get("enabled"):
        if service_states.get("zaojiazhisuan-feishu-bot.service") != "active":
            errors.append(
                "zaojiazhisuan-feishu-bot.service 当前状态不是 active："
                f"{service_states.get('zaojiazhisuan-feishu-bot.service') or '未知'}"
            )
        if not bot_status.get("running"):
            errors.append("第二层机器人已启用，但等待 30 秒后仍未进入 running 状态")
    return errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查第二层机器人本地 / 云端专业服务地址与健康状态。")
    parser.add_argument("--mode", choices=("local", "cloud"), required=True, help="部署环境。")
    parser.add_argument("--check-health", action="store_true", help="同时请求对应 /api/health。")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        project_default = read_project_default_api_base_url()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] 无法读取项目默认配置：{exc}")
        return 1

    if args.mode == "local":
        environment_value = normalize_url(os.getenv(ENVIRONMENT_KEY))
        errors = validate_local(project_default, environment_value)
        target_url = environment_value or project_default
        print(f"[INFO] mode=local project_default={project_default} effective={target_url}")
    else:
        service_values: dict[str, str] = {}
        service_states: dict[str, str] = {}
        try:
            for service in CLOUD_SERVICES:
                service_values[service] = read_systemd_environment(service)
                service_states[service] = read_systemd_state(service)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"[FAIL] 无法读取 systemd 服务配置：{exc}")
            return 1
        errors = validate_cloud(project_default, service_values)
        for service in CLOUD_SERVICES:
            print(
                f"[INFO] service={service} state={service_states[service]} "
                f"api_base_url={service_values[service] or '未设置'}"
            )
        target_url = CLOUD_API_BASE_URL

    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1

    if args.check_health:
        try:
            version = check_health(target_url)
        except RuntimeError as exc:
            print(f"[FAIL] {exc}")
            return 1
        print(f"[OK] 专业服务健康，version={version}，api_base_url={target_url}")
    else:
        print(f"[OK] 部署地址检查通过，api_base_url={target_url}")
    if args.mode == "cloud":
        try:
            bot_status = wait_for_bot_status(target_url)
        except RuntimeError as exc:
            print(f"[FAIL] {exc}")
            return 1
        runtime_errors = validate_cloud_runtime(service_states, bot_status)
        if runtime_errors:
            for error in runtime_errors:
                print(f"[FAIL] {error}")
            return 1
        print(
            "[OK] 第二层机器人运行态通过，"
            f"enabled={bool(bot_status.get('enabled'))}，"
            f"running={bool(bot_status.get('running'))}，"
            f"active_profile={bot_status.get('active_profile') or '未选择'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

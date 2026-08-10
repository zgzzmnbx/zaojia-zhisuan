from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import time
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CREDENTIALS_PATH = (
    PROJECT_ROOT / "Codex-Temp/runtime/cloud-deployment-credentials.json"
)
REMOTE_ROOT = "/opt/zaojiazhisuan"
API_BASE_URL = "http://127.0.0.1:1285"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def effective_release_version(payload: dict[str, Any]) -> str:
    return str(payload.get("release_version") or payload.get("version") or "").strip()


def profiles_are_converged(payload: dict[str, Any]) -> bool:
    profiles = payload.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        return False
    for profile in profiles:
        if not isinstance(profile, dict):
            return False
        enabled = bool(profile.get("enabled"))
        running = bool(profile.get("running"))
        if enabled != running:
            return False
        if enabled and not bool(profile.get("profile_consistent")):
            return False
    return True


def load_credentials(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = ("host", "username", "password")
    missing = [key for key in required if not str(payload.get(key) or "").strip()]
    if missing:
        raise ValueError(f"云端凭据缺少字段：{', '.join(missing)}")
    return payload


def connect(credentials_path: Path):
    try:
        import paramiko
    except ImportError as exc:  # pragma: no cover - depends on workstation runtime
        raise RuntimeError("本机缺少 paramiko，请先执行 python -m pip install paramiko") from exc

    credentials = load_credentials(credentials_path)
    latest_error: Exception | None = None
    for attempt in range(1, 4):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=credentials["host"],
                port=int(credentials.get("port", 22)),
                username=credentials["username"],
                password=credentials["password"],
                timeout=20,
                banner_timeout=20,
                auth_timeout=20,
            )
            return client
        except (OSError, paramiko.SSHException) as exc:
            latest_error = exc
            client.close()
            if attempt < 3:
                time.sleep(attempt * 2)
    raise RuntimeError(f"SSH 连接连续 3 次失败：{latest_error}") from latest_error


def run(client, command: str, *, check: bool = True, timeout: int = 180) -> str:
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    output = stdout.read().decode("utf-8", errors="replace").strip()
    error = stderr.read().decode("utf-8", errors="replace").strip()
    status = stdout.channel.recv_exit_status()
    if check and status != 0:
        detail = error or output or f"exit={status}"
        raise RuntimeError(detail[-3000:])
    return output


def upload_file(client, local_path: Path, remote_path: str) -> None:
    sftp = client.open_sftp()
    try:
        sftp.put(str(local_path), remote_path)
    finally:
        sftp.close()


def read_json_endpoint(client, path: str) -> dict[str, Any]:
    raw = run(
        client,
        f"curl -fsS --max-time 10 {shlex.quote(API_BASE_URL + path)}",
        check=False,
    )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw[:300]}
    return payload if isinstance(payload, dict) else {"raw": raw[:300]}


def service_snapshot(client) -> dict[str, Any]:
    bot = read_json_endpoint(client, "/api/collaboration/feishu-app-bot/status")
    profiles: list[dict[str, Any]] = []
    raw_profiles = bot.get("profiles")
    if isinstance(raw_profiles, list):
        for profile in raw_profiles:
            if not isinstance(profile, dict):
                continue
            profiles.append(
                {
                    key: profile.get(key)
                    for key in (
                        "profile_id",
                        "label",
                        "enabled",
                        "running",
                        "configured",
                        "profile_consistent",
                        "pid",
                    )
                    if key in profile
                }
            )
    return {
        "uid": run(client, "id -u"),
        "current": run(client, f"readlink -f {REMOTE_ROOT}/current", check=False),
        "main_service": run(
            client, "systemctl is-active zaojiazhisuan.service", check=False
        ),
        "supervisor_enabled": run(
            client,
            "systemctl is-enabled zaojiazhisuan-feishu-bot.service",
            check=False,
        ),
        "supervisor_active": run(
            client,
            "systemctl is-active zaojiazhisuan-feishu-bot.service",
            check=False,
        ),
        "runner_count": int(
            run(client, "pgrep -fc '[f]eishu_bot_runner.py' || true", check=False)
            or "0"
        ),
        "health": read_json_endpoint(client, "/api/health"),
        "bot": {
            "enabled": bot.get("enabled"),
            "running": bot.get("running"),
            "profile_consistent": bot.get("profile_consistent"),
            "running_profile_count": bot.get("running_profile_count"),
            "profiles": profiles,
        },
    }


def wait_for_health(client, expected_version: str, attempts: int = 45) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for _ in range(attempts):
        latest = read_json_endpoint(client, "/api/health")
        if (
            latest.get("status") == "ok"
            and effective_release_version(latest) == expected_version
        ):
            return latest
        time.sleep(2)
    raise RuntimeError(f"健康检查未达到 {expected_version}：{latest}")


def wait_for_profiles(client, attempts: int = 30) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for _ in range(attempts):
        latest = read_json_endpoint(
            client, "/api/collaboration/feishu-app-bot/status"
        )
        if profiles_are_converged(latest):
            return latest
        time.sleep(1)
    raise RuntimeError(f"双平台运行器状态未收敛：{latest}")


def rollback(client, previous: str) -> None:
    if not previous:
        return
    run(client, f"ln -sfn {shlex.quote(previous)} {REMOTE_ROOT}/current", check=False)
    run(
        client,
        f"bash {REMOTE_ROOT}/current/deploy/install_cloud_runtime_guard.sh {REMOTE_ROOT}/current",
        check=False,
        timeout=300,
    )
    run(client, "systemctl daemon-reload", check=False)
    run(client, "systemctl restart zaojiazhisuan.service", check=False)
    run(
        client,
        "systemctl enable --now zaojiazhisuan-feishu-bot.service",
        check=False,
    )


def publish(args: argparse.Namespace) -> dict[str, Any]:
    archive = args.archive.resolve()
    if not archive.is_file():
        raise FileNotFoundError(f"发布包不存在：{archive}")
    local_sha = sha256_file(archive)
    if args.sha256 and local_sha != args.sha256.upper():
        raise RuntimeError("本地发布包 SHA256 与指定值不一致")

    release_name = args.release_name or (
        f"{datetime.now():%Y%m%d-%H%M%S}-{args.expected_version}-cloud-release"
    )
    new_release = f"{REMOTE_ROOT}/releases/{release_name}"
    remote_archive = f"/tmp/{release_name}.tar.gz"
    client = connect(args.credentials.resolve())
    switched = False
    previous = ""
    try:
        before = service_snapshot(client)
        if before["uid"] != "0":
            raise RuntimeError("云端发布账号不是 root，拒绝继续")
        previous = str(before.get("current") or "")
        if not previous.startswith(f"{REMOTE_ROOT}/releases/"):
            raise RuntimeError(f"无法确认可回滚的 current：{previous or '空'}")
        exists = run(
            client,
            f"test -e {shlex.quote(new_release)}; echo $?",
            check=False,
        )
        if exists.strip() == "0":
            raise RuntimeError(f"新发布目录已存在，拒绝覆盖：{new_release}")

        upload_file(client, archive, remote_archive)
        remote_sha = run(
            client,
            f"sha256sum {shlex.quote(remote_archive)} | awk '{{print toupper($1)}}'",
        )
        if remote_sha != local_sha:
            raise RuntimeError("上传后发布包 SHA256 不一致")

        run(client, f"mkdir -p {shlex.quote(new_release)}")
        run(
            client,
            f"tar -xzf {shlex.quote(remote_archive)} -C {shlex.quote(new_release)}",
            timeout=300,
        )
        run(client, f"mkdir -p {shlex.quote(new_release + '/Codex-Temp')}")
        run(
            client,
            "if test -d {old}; then cp -a {old} {new}; "
            "else mkdir -p {new_runtime}; fi".format(
                old=shlex.quote(previous + "/Codex-Temp/runtime"),
                new=shlex.quote(new_release + "/Codex-Temp/"),
                new_runtime=shlex.quote(new_release + "/Codex-Temp/runtime"),
            ),
            timeout=300,
        )
        run(
            client,
            "if test -f {old}; then cp -a {old} {new}; fi".format(
                old=shlex.quote(previous + "/.env.local"),
                new=shlex.quote(new_release + "/.env.local"),
            ),
        )
        run(
            client,
            f"{REMOTE_ROOT}/venv/bin/python {shlex.quote(new_release + '/tools/check_cloud_release.py')} "
            f"--release-root {shlex.quote(new_release)}",
            timeout=300,
        )
        run(
            client,
            f"{REMOTE_ROOT}/venv/bin/pip install -r "
            f"{shlex.quote(new_release + '/backend/requirements-runtime.txt')}",
            timeout=600,
        )

        run(client, f"ln -sfn {shlex.quote(new_release)} {REMOTE_ROOT}/current")
        switched = True
        run(
            client,
            f"bash {REMOTE_ROOT}/current/deploy/install_cloud_runtime_guard.sh {REMOTE_ROOT}/current",
            timeout=300,
        )
        run(client, "systemctl daemon-reload")
        run(client, "systemctl restart zaojiazhisuan.service")
        health = wait_for_health(client, args.expected_version)
        run(client, "systemctl enable --now zaojiazhisuan-feishu-bot.service")
        profiles = wait_for_profiles(client)
        deployment_check = run(
            client,
            f"cd {REMOTE_ROOT}/current && {REMOTE_ROOT}/venv/bin/python "
            "tools/check_feishu_deployment.py --mode cloud --check-health",
            timeout=180,
        )
        after = service_snapshot(client)
        if after["current"] != new_release:
            raise RuntimeError(f"current 指向异常：{after['current']}")
        if after["main_service"] != "active" or after["supervisor_active"] != "active":
            raise RuntimeError(f"systemd 服务状态异常：{after}")
        return {
            "release": new_release,
            "rollback": previous,
            "sha256": local_sha,
            "health": health,
            "profiles": profiles.get("profiles"),
            "deployment_check_tail": deployment_check[-1600:],
            "before": before,
            "after": after,
        }
    except Exception:
        if switched:
            rollback(client, previous)
        raise
    finally:
        run(client, f"rm -f {shlex.quote(remote_archive)}", check=False)
        client.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="上传、切换、验证并在失败时回滚造价智算云端发布包。"
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=DEFAULT_CREDENTIALS_PATH,
        help="Git 忽略的云端凭据 JSON。",
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)
    subparsers.add_parser("preflight", help="只读发布前服务与双平台状态。")
    deploy = subparsers.add_parser("publish", help="执行完整发布与失败回滚。")
    deploy.add_argument("--archive", type=Path, required=True)
    deploy.add_argument("--sha256", help="可选，指定本地构建器输出的 SHA256。")
    deploy.add_argument("--expected-version", required=True, help="例如 v5.19.7。")
    deploy.add_argument("--release-name", help="可选，默认使用当前时间生成唯一目录。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode == "preflight":
        client = connect(args.credentials.resolve())
        try:
            result = service_snapshot(client)
        finally:
            client.close()
    else:
        result = publish(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

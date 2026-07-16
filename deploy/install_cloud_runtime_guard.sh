#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SOURCE_FILE="${PROJECT_ROOT}/deploy/systemd/feishu-api-base.conf"
SERVICES=(zaojiazhisuan.service zaojiazhisuan-feishu-bot.service)

if [[ "$(id -u)" -ne 0 ]]; then
  echo "错误：请使用 root 运行云端运行环境加固脚本。" >&2
  exit 1
fi

if [[ ! -f "${SOURCE_FILE}" ]]; then
  echo "错误：未找到仓库内 systemd 配置：${SOURCE_FILE}" >&2
  exit 1
fi

for service in "${SERVICES[@]}"; do
  install -D -m 0644 "${SOURCE_FILE}" "/etc/systemd/system/${service}.d/api-base.conf"
done

systemctl daemon-reload
echo "已为主服务和第二层机器人安装云端 1285 端口保护。"

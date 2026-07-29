#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SOURCE_FILE="${PROJECT_ROOT}/deploy/systemd/feishu-api-base.conf"
SUPERVISOR_UNIT_SOURCE="${PROJECT_ROOT}/deploy/systemd/zaojiazhisuan-feishu-bot.service"
SERVICES=(zaojiazhisuan.service zaojiazhisuan-feishu-bot.service)

if [[ "$(id -u)" -ne 0 ]]; then
  echo "错误：请使用 root 运行云端运行环境加固脚本。" >&2
  exit 1
fi

if [[ ! -f "${SOURCE_FILE}" ]]; then
  echo "错误：未找到仓库内 systemd 配置：${SOURCE_FILE}" >&2
  exit 1
fi
if [[ ! -f "${SUPERVISOR_UNIT_SOURCE}" ]]; then
  echo "错误：未找到双平台监督器 systemd 单元：${SUPERVISOR_UNIT_SOURCE}" >&2
  exit 1
fi

for service in "${SERVICES[@]}"; do
  install -D -m 0644 "${SOURCE_FILE}" "/etc/systemd/system/${service}.d/api-base.conf"
done
install -D -m 0644 "${SUPERVISOR_UNIT_SOURCE}" \
  "/etc/systemd/system/zaojiazhisuan-feishu-bot.service"

systemctl daemon-reload
echo "已安装双平台长连接监督器，并为主服务和监督器配置云端 1285 端口保护。"

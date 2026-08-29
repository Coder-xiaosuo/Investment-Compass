#!/bin/bash
# PA Agent 投资分析服务 - 生产启动脚本
# 用法: ./start.sh [--reload]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RELOAD="${1:-}"

# 环境变量检查
# DEEPSEEK_API_KEY 现已通过前端「系统设置」界面配置（加密存储于 config/settings.json）
# 此处仅做提示，不阻塞启动
if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
    echo "[INFO] DEEPSEEK_API_KEY 环境变量未设置，请在启动后通过前端「系统设置」界面配置 API Key"
fi
: "${DATABASE_URL:?请设置 DATABASE_URL 环境变量（如未设置，使用 .env 中配置）}"

# 日志目录
mkdir -p logs

LOG_LEVEL="${LOG_LEVEL:-INFO}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8002}"
WORKERS="${WORKERS:-1}"

echo "=== PA Agent 投资分析服务 ==="
echo "  HOST:      $HOST"
echo "  PORT:      $PORT"
echo "  WORKERS:   $WORKERS"
echo "  LOG_LEVEL: $LOG_LEVEL"
echo "  RELOAD:    ${RELOAD:-no}"
echo ""

exec uvicorn main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level "${LOG_LEVEL,,}" \
    --log-config <(cat <<PYEOF
version: 1
formatters:
  default:
    format: '%(asctime)s %(levelname)-5s %(name)s %(message)s'
    datefmt: '%Y-%m-%d %H:%M:%S'
handlers:
  console:
    class: logging.StreamHandler
    formatter: default
    stream: ext://sys.stdout
  file:
    class: logging.handlers.RotatingFileHandler
    formatter: default
    filename: logs/pa-agent.log
    maxBytes: 10485760
    backupCount: 5
loggers:
  uvicorn:
    level: INFO
    handlers: [console, file]
    propagate: no
  pa_analyzer:
    level: ${LOG_LEVEL}
    handlers: [console, file]
    propagate: no
  services:
    level: ${LOG_LEVEL}
    handlers: [console, file]
    propagate: no
  agents:
    level: ${LOG_LEVEL}
    handlers: [console, file]
    propagate: no
  root:
    level: WARNING
    handlers: [console, file]
PYEOF
) \
    ${RELOAD:+--reload}

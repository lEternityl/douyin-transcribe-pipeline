#!/usr/bin/env bash
# 启动抖音下载/转写流水线所有服务: Redis + FastAPI + arq worker + Vite 前端
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
LOG_DIR="$ROOT/.logs"
mkdir -p "$LOG_DIR"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }

# 端口占用检查
port_in_use() { lsof -iTCP:"$1" -sTCP:LISTEN -P -n >/dev/null 2>&1; }

# --foreground/-f: 前台阻塞等待子进程(适合容器/调试)
# 默认: 后台启动并立即返回(适合终端交互)
FOREGROUND=0
if [ "$1" = "--foreground" ] || [ "$1" = "-f" ]; then
  FOREGROUND=1
fi
# 后台模式才 disown(前台模式需保留子进程关系以便 wait)
maybe_disown() {
  if [ "$FOREGROUND" -eq 0 ]; then
    disown 2>/dev/null || true
  fi
}

# === 1. Redis ===
if port_in_use 6379; then
  ok "Redis 已在运行 :6379"
else
  if command -v redis-server >/dev/null 2>&1; then
    redis-server --daemonize yes --port 6379
    sleep 1
    ok "Redis 已启动 :6379"
  else
    err "未找到 redis-server,请先 brew install redis"
    exit 1
  fi
fi

# === 2. FastAPI (uvicorn) ===
if port_in_use 8000; then
  warn "8000 端口已占用,跳过 uvicorn 启动"
else
  cd "$BACKEND"
  nohup uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 \
    < /dev/null > "$LOG_DIR/uvicorn.log" 2>&1 &
  maybe_disown
  echo $! > "$LOG_DIR/uvicorn.pid"
  cd "$ROOT"
  ok "FastAPI 已启动 :8000 (pid $(cat "$LOG_DIR/uvicorn.pid")) -> $LOG_DIR/uvicorn.log"
fi

# === 3. arq worker ===
if pgrep -f "arq app.workers.arq_app.WorkerSettings" >/dev/null 2>&1; then
  warn "arq worker 已在运行,跳过"
else
  cd "$BACKEND"
  nohup uv run arq app.workers.arq_app.WorkerSettings \
    < /dev/null > "$LOG_DIR/arq.log" 2>&1 &
  maybe_disown
  echo $! > "$LOG_DIR/arq.pid"
  cd "$ROOT"
  ok "arq worker 已启动 (pid $(cat "$LOG_DIR/arq.pid")) -> $LOG_DIR/arq.log"
fi

# === 4. Vite 前端 ===
if port_in_use 5173; then
  warn "5173 端口已占用,跳过 Vite 启动"
else
  cd "$FRONTEND"
  if [ -d node_modules ]; then
    nohup pnpm dev --port 5173 --host 127.0.0.1 \
      < /dev/null > "$LOG_DIR/vite.log" 2>&1 &
  else
    warn "node_modules 不存在,先初始化..."
    pnpm install
    nohup pnpm dev --port 5173 --host 127.0.0.1 \
      < /dev/null > "$LOG_DIR/vite.log" 2>&1 &
  fi
  maybe_disown
  echo $! > "$LOG_DIR/vite.pid"
  cd "$ROOT"
  ok "Vite 已启动 :5173 (pid $(cat "$LOG_DIR/vite.pid")) -> $LOG_DIR/vite.log"
fi

echo ""
ok "全部服务已启动:"
echo "    Redis      :  http://127.0.0.1:6379"
echo "    FastAPI    :  http://127.0.0.1:8000/docs"
echo "    前端       :  http://localhost:5173"
echo ""
echo "日志目录: $LOG_DIR/"
echo "停止服务: ./stop.sh"

# --foreground: 前台阻塞,等待所有后台子进程(适合容器/调试)
# 默认(无参数): 后台启动并立即返回(适合终端交互)
if [ "$FOREGROUND" -eq 1 ]; then
  echo ""
  warn "前台模式,等待子进程... (Ctrl+C 或 ./stop.sh 退出)"
  wait
fi

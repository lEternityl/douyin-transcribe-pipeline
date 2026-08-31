#!/usr/bin/env bash
# 停止抖音下载/转写流水线所有服务: Vite + arq worker + FastAPI + Redis
# 不动 Redis 之外其它依赖(如 mysql 等),只关本项目相关进程

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT/.logs"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }

stop_by_pidfile() {
  local name="$1"
  local pidfile="$LOG_DIR/$2"
  if [ -f "$pidfile" ]; then
    local pid
    pid="$(cat "$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 1
      # 仍在则强杀
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
      ok "$name 已停止 (pid $pid)"
    else
      warn "$name 进程已不存在 (pid $pid)"
    fi
    rm -f "$pidfile"
  fi
}

stop_by_pattern() {
  local name="$1"
  local pattern="$2"
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    pkill -f "$pattern" 2>/dev/null || true
    sleep 1
    if pgrep -f "$pattern" >/dev/null 2>&1; then
      pkill -9 -f "$pattern" 2>/dev/null || true
    fi
    ok "$name 已停止"
  fi
}

echo "停止抖音流水线服务..."

# === 1. Vite 前端 ===
stop_by_pidfile "Vite" "vite.pid"
stop_by_pattern  "Vite (pkill 兜底)" "vite"

# === 2. arq worker ===
stop_by_pidfile "arq worker" "arq.pid"
stop_by_pattern  "arq (pkill 兜底)" "arq app.workers.arq_app.WorkerSettings"

# === 3. FastAPI (uvicorn) ===
stop_by_pidfile "FastAPI" "uvicorn.pid"
stop_by_pattern  "FastAPI (pkill 兜底)" "uvicorn app.main:app"

# === 4. Redis (默认停止) ===
if [ "$1" = "--with-redis" ] || [ "$1" = "--all" ]; then
  if command -v redis-cli >/dev/null 2>&1; then
    redis-cli shutdown nosave 2>/dev/null && ok "Redis 已停止" || warn "Redis 未运行或无法停止"
  fi
else
  if pgrep -f "redis-server" >/dev/null 2>&1; then
    warn "Redis 仍在运行(保留,如需停止: ./stop.sh --with-redis)"
  fi
fi

echo ""
ok "完成。"

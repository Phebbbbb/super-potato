#!/bin/bash
# ============================================================
# 一键启动脚本 — 开发 / 生产 / 恢复
# 用法:
#   bash scripts/start.sh dev      # 开发模式 (后端+前端热重载)
#   bash scripts/start.sh prod     # 生产模式 (docker compose up -d)
#   bash scripts/start.sh restore  # 恢复最近备份
# ============================================================

set -e

MODE="${1:-dev}"

case "$MODE" in
    dev)
        echo "=== 启动开发环境 ==="
        cd backend
        uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
        BACKEND_PID=$!
        cd ../frontend
        npm run dev &
        FRONTEND_PID=$!
        cd ..

        echo ""
        echo "后端: http://localhost:8000 (PID: $BACKEND_PID)"
        echo "前端: http://localhost:5173 (PID: $FRONTEND_PID)"
        echo ""
        echo "按 Ctrl+C 停止所有服务"

        trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
        wait
        ;;

    prod)
        echo "=== 启动生产环境 ==="
        if ! command -v docker &>/dev/null; then
            echo "错误: 未安装 Docker"
            exit 1
        fi
        docker compose up -d
        echo ""
        echo "服务已启动:"
        docker compose ps
        echo ""
        echo "查看日志: docker compose logs -f"
        ;;

    restore)
        echo "=== 恢复最近备份 ==="
        BACKUP_DIR="${BACKUP_DIR:-backups}"
        LATEST=$(ls -t "$BACKUP_DIR"/smarttax_* 2>/dev/null | head -1)
        if [ -z "$LATEST" ]; then
            echo "错误: 没有找到备份文件"
            exit 1
        fi
        echo "最近备份: $LATEST"
        echo ""
        echo "警告: 恢复操作会覆盖当前数据库！"
        echo -n "确认恢复? [y/N]: "
        read -r CONFIRM
        if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
            echo "已取消"
            exit 0
        fi

        DB_URL="${DATABASE_URL:-sqlite:///./smart_tax.db}"

        if echo "$LATEST" | grep -q "\.sql\.gz$"; then
            # PostgreSQL 恢复
            DB_NAME=$(echo "$DB_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')
            gunzip -c "$LATEST" | psql -d "$DB_NAME"
        else
            # SQLite 恢复
            DB_PATH=$(echo "$DB_URL" | sed 's|sqlite:///||')
            gunzip -c "$LATEST" > "$DB_PATH"
        fi
        echo "恢复完成: $LATEST → 数据库"
        ;;

    *)
        echo "用法: bash scripts/start.sh {dev|prod|restore}"
        exit 1
        ;;
esac

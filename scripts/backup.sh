#!/bin/bash
# ============================================================
# 数据库备份脚本 — 保留近 7 天
# 用法: bash scripts/backup.sh
# cron: 0 2 * * * bash /app/scripts/backup.sh
# ============================================================

set -e

BACKUP_DIR="${BACKUP_DIR:-backups}"
DB_URL="${DATABASE_URL:-sqlite:///./smart_tax.db}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

echo "=== 数据库备份 $(date '+%Y-%m-%d %H:%M:%S') ==="

# 判断数据库类型并备份
if echo "$DB_URL" | grep -q "^postgresql://"; then
    # PostgreSQL: pg_dump
    BACKUP_FILE="$BACKUP_DIR/smarttax_$TIMESTAMP.sql.gz"
    # 从 DATABASE_URL 解析连接参数
    DB_HOST=$(echo "$DB_URL" | sed -n 's|.*@\([^:]*\).*|\1|p')
    DB_PORT=$(echo "$DB_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
    DB_NAME=$(echo "$DB_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')
    DB_USER=$(echo "$DB_URL" | sed -n 's|.*://\([^:]*\).*|\1|p')
    PGPASSWORD=$(echo "$DB_URL" | sed -n 's|.*://[^:]*:\(.*\)@.*|\1|p')

    echo "PostgreSQL: $DB_USER@$DB_HOST:$DB_PORT/$DB_NAME → $BACKUP_FILE"
    PGPASSWORD="$PGPASSWORD" pg_dump \
        -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "$DB_USER" -d "$DB_NAME" \
        --no-owner --no-acl | gzip > "$BACKUP_FILE"

elif echo "$DB_URL" | grep -q "^sqlite:///"; then
    # SQLite: 直接文件复制
    DB_PATH=$(echo "$DB_URL" | sed 's|sqlite:///||')
    BACKUP_FILE="$BACKUP_DIR/smarttax_$TIMESTAMP.db.gz"
    echo "SQLite: $DB_PATH → $BACKUP_FILE"
    if [ -f "$DB_PATH" ]; then
        sqlite3 "$DB_PATH" ".backup /dev/stdout" | gzip > "$BACKUP_FILE"
    else
        echo "警告: 数据库文件 $DB_PATH 不存在"
        exit 1
    fi
else
    echo "错误: 不支持的数据库 URL: $DB_URL"
    exit 1
fi

# 大小
SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "备份完成: $BACKUP_FILE ($SIZE)"

# 清理超过 7 天的备份
echo "清理 ${RETENTION_DAYS} 天前的旧备份..."
find "$BACKUP_DIR" -name "smarttax_*" -mtime "+$RETENTION_DAYS" -delete

echo "当前备份数: $(ls "$BACKUP_DIR"/smarttax_* 2>/dev/null | wc -l)"
echo "=== 备份结束 ==="

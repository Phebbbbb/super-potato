#!/bin/bash
# ============================================================
# 健康检查脚本 — 供 Hermes cron 调用 / 手动运维
# 用法: bash scripts/health_check.sh [base_url]
# 返回: 0 = 全部健康, 1 = 有异常
# ============================================================

BASE_URL="${1:-http://localhost}"
TIMEOUT=10
FAILURES=0

red()  { echo -e "\033[31m$1\033[0m"; }
green(){ echo -e "\033[32m$1\033[0m"; }

check_url() {
    local label="$1" url="$2"
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" "$url" 2>/dev/null)
    if [ "$code" = "200" ] || [ "$code" = "401" ] || [ "$code" = "307" ]; then
        green "  ✓ $label ($code)"
    else
        red "  ✗ $label (HTTP $code)"
        FAILURES=$((FAILURES + 1))
    fi
}

echo "=== 健康检查 $(date '+%Y-%m-%d %H:%M:%S') ==="
echo "目标: $BASE_URL"
echo ""

# 1. 前端 (nginx)
check_url "前端首页"      "$BASE_URL/"

# 2. 后端 API
check_url "后端 API"      "$BASE_URL/api/"
check_url "税务申报"      "$BASE_URL/api/filings/"

# 3. 数据库连通 (通过后端健康接口)
HEALTH=$(curl -s --connect-timeout "$TIMEOUT" "$BASE_URL/api/health" 2>/dev/null)
if echo "$HEALTH" | grep -qi "ok\|healthy"; then
    green "  ✓ 数据库连通"
else
    red "  ✗ 数据库连通 (健康检查失败)"
    FAILURES=$((FAILURES + 1))
fi

echo ""
echo "---"
if [ "$FAILURES" -eq 0 ]; then
    green "全部服务健康 ✓"
    exit 0
else
    red "发现 $FAILURES 个异常 ✗"
    exit 1
fi

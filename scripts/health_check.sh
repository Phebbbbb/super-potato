#!/usr/bin/env bash
# Health check — frontend (Vite), backend API, database connectivity
FRONTEND_URL="${FRONTEND_URL:-http://localhost:5173}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
TIMEOUT_SEC=10
ALERTS=0

red()   { printf '\033[31m%s\033[0m\n' "$1"; }
green() { printf '\033[32m%s\033[0m\n' "$1"; }

echo "=== SmartTax Health Check $(date '+%Y-%m-%d %H:%M:%S') ==="
echo ""

# ---- Frontend (Vite dev server) ----
echo -n "Frontend ($FRONTEND_URL) ... "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT_SEC" "$FRONTEND_URL" 2>/dev/null)
if [ "$HTTP_CODE" = "200" ]; then
    green "OK (200)"
else
    red "DOWN — cannot reach $FRONTEND_URL (HTTP $HTTP_CODE)"
    ALERTS=$((ALERTS + 1))
fi

# ---- Backend health endpoint ----
echo -n "Backend  ($BACKEND_URL/api/health) ... "
HEALTH=$(curl -s --max-time "$TIMEOUT_SEC" "$BACKEND_URL/api/health" 2>/dev/null || echo '{"status":"fail"}')
STATUS=$(echo "$HEALTH" | grep -o '"status":"[^"]*"' | head -1 | sed 's/"status":"//;s/"//')
if [ "$STATUS" = "ok" ]; then
    green "OK (status=ok)"
else
    red "DOWN — health check failed: $HEALTH"
    ALERTS=$((ALERTS + 1))
fi

# ---- Database (via backend health) ----
echo -n "Database (via backend) ... "
if echo "$HEALTH" | grep -q '"status":"ok"'; then
    green "OK (connected)"
else
    red "DOWN — backend cannot reach database"
    ALERTS=$((ALERTS + 1))
fi

echo ""
if [ "$ALERTS" -eq 0 ]; then
    green "All services healthy"
    exit 0
else
    red "ALERT: $ALERTS service(s) down — immediate attention required!"
    exit 1
fi

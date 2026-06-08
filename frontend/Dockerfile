# 前端 — 多阶段构建 (tsc + vite + nginx)
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ===== 生产运行时 =====
FROM nginx:alpine

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制 nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 健康检查端点
RUN mkdir -p /usr/share/nginx/html/health && \
    echo "ok" > /usr/share/nginx/html/health/index.html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

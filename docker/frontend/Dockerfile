# syntax=docker/dockerfile:1.7
# Build stage: install + tsc + vite build
FROM node:22-alpine AS builder
WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# Runtime stage: nginx
FROM nginx:1.27-alpine AS runtime
COPY docker/frontend/nginx.conf /etc/nginx/nginx.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

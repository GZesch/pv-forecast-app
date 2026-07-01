FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml README.md ./
RUN uv sync --no-dev --no-install-project

COPY backend ./backend
COPY frontend ./frontend
COPY scripts/verify_bdew_h25.py ./scripts/verify_bdew_h25.py

FROM base AS backend
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS frontend
EXPOSE 8501
CMD ["uv", "run", "--no-sync", "streamlit", "run", "frontend/app.py", "--server.address=0.0.0.0", "--server.port=8501"]

FROM node:24-alpine AS web-dependencies

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH

RUN corepack enable && corepack prepare pnpm@11.7.0 --activate

WORKDIR /app/web

COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM web-dependencies AS web-builder

ARG NEXT_PUBLIC_SITE_URL=http://exergypulse.localhost
ARG NEXT_PUBLIC_PV_FORECAST_URL=http://forecast.localhost
ENV NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL
ENV NEXT_PUBLIC_PV_FORECAST_URL=$NEXT_PUBLIC_PV_FORECAST_URL

COPY web/ ./
RUN pnpm build

FROM node:24-alpine AS web

ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000

WORKDIR /app

COPY --from=web-builder --chown=node:node /app/web/.next/standalone ./
COPY --from=web-builder --chown=node:node /app/web/.next/static ./.next/static

USER node

EXPOSE 3000
CMD ["node", "server.js"]

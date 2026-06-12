# DevTrack

项目管理与问题跟踪平台。Django REST Framework 后端 + Nuxt 4 SPA 前端，JWT 认证。

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Python 3.14, Django 6.0, DRF 3.15 |
| 前端 | Nuxt 4, Vue 3 (SPA 模式) |
| 数据库 | PostgreSQL |
| 对象存储 | MinIO (S3 兼容) |
| 反向代理 | Traefik |
| CI/CD | GitHub Actions + Watchtower |
| 容器 | Docker |

## 本地开发

### 后端 (在 `backend/` 下运行)

```bash
uv sync --dev                              # 安装依赖
uv run python manage.py migrate            # 执行迁移
uv run python manage.py sync_page_perms    # 同步页面路由和权限组
uv run python manage.py loaddata fixtures/ai_prompts.json  # 加载 AI 提示词种子数据
uv run python manage.py createsuperuser    # 创建管理员
uv run python manage.py runserver          # 启动开发服务器 :8000
```

### 前端 (在 `frontend/` 下运行)

```bash
npm install
npm run dev                                # 启动开发服务器 :3004
```

### Docker 一键启动

```bash
docker compose up --build                  # 后端 :8000, 前端 :3000
```

## 生产部署

### 架构概览

```
用户 → Traefik ─┬─ /api/* → backend:8000 (Django)
                └─ /*     → frontend:3000 (Node)

backend → PostgreSQL (外部)
        → MinIO (对象存储)
        → DeepSeek API (AI 分析)
        → GitHub API (仓库同步)
```

### CI/CD 流程

推送到 `env/test` 或 `env/prod` 分支触发 GitHub Actions (`.github/workflows/build-push.yml`)：

```bash
git push -f origin main:env/test     # 部署到测试环境
git push -f origin main:env/prod     # 部署到生产环境
```

`env/test` 和 `env/prod` 是发布分支，只反映当前部署的内容，始终从 `main` 强推。

**构建过程：**

1. 根据分支确定环境 (`test` / `prod`)
2. 生成 `VERSION` 文件（两段式格式：`env/<环境> <git短SHA>`）
3. 并行构建后端和前端 Docker 镜像（buildx + GitHub Actions 层缓存；同一 SHA 的镜像已存在时跳过构建，直接提升为 `latest`）
4. 推送到私有镜像仓库 `registry.cktech.hk/devtrakr/{backend,frontend}-{env}`
5. 通过 Day.app webhook 发送构建通知

**服务端自动更新：** Watchtower 监听镜像更新，自动拉取并重启容器。

### Docker 镜像

**后端** (`backend/Dockerfile`)：

- 基于 `python:3.14-slim`
- 安装 git、curl、postgresql-client、opencode (AI 代码分析工具)
- 使用 uv 管理依赖，`collectstatic` 打包静态文件 (WhiteNoise 伺服)
- 容器内统一 `uv run --no-sync`，启动时不联网重装依赖

**前端** (`frontend/Dockerfile`)：

- 多阶段构建，基于 `node:22-slim`
- 依赖用 `npm ci` 按 lockfile 安装，保证构建可复现
- 构建时通过 `NUXT_API_BASE` 指定后端地址 (默认 `http://backend:8000`)
- 运行阶段仅包含 `.output` 产物

### 服务器部署

部署配置以仓库 `deploy/{env}/`（`test` / `prod`）为源，同步到服务器对应目录：

```
deploy/{env}/
├── docker-compose.yml    # 服务编排（仓库内为源，改动需手动同步到服务器）
├── .env                  # 环境变量（仅存服务器，不入库）
└── .gitconfig-proxy      # Git 代理配置 (仅 prod，用于仓库克隆)
```

**docker-compose.yml** 要点（完整文件见 `deploy/test/docker-compose.yml`）：

```yaml
services:
  backend:
    image: registry.cktech.hk/devtrakr/backend-{env}
    env_file: .env
    volumes:                                          # 仅 prod
      - ./.gitconfig-proxy:/root/.gitconfig:ro        # Git 代理
      - repo_data:/data/repos                         # 克隆的仓库
    command: >
      sh -c "uv run --no-sync python manage.py migrate --noinput &&
             uv run --no-sync python manage.py sync_page_perms 2>/dev/null || true &&
             uv run --no-sync python manage.py runserver 0.0.0.0:8000"
             # prod 为 uvicorn config.asgi:application --workers 4
    labels:
      - com.centurylinklabs.watchtower.enable=true
      - "traefik.http.routers.devtrakr-backend.rule=Host(`<域名>`) && PathPrefix(`/api`)"

  frontend:
    image: registry.cktech.hk/devtrakr/frontend-{env}
    depends_on: [backend]
    labels:
      - com.centurylinklabs.watchtower.enable=true
      - "traefik.http.routers.devtrakr-frontend.rule=Host(`<域名>`)"

  celery-worker:    # 异步任务
    image: registry.cktech.hk/devtrakr/backend-{env}
    command: uv run --no-sync celery -A config worker -l info

  celery-beat:      # 定时任务
    image: registry.cktech.hk/devtrakr/backend-{env}
    command: uv run --no-sync celery -A config beat -l info --scheduler django_celery_beat.schedulers.DatabaseScheduler

networks:
  db-network:
    external: true
  traefik-network:
    external: true
```

容器启动时自动执行 `migrate` 和 `sync_page_perms`。注意：Watchtower 只自动拉取新镜像，compose 文件改动不会自动生效，需手动同步到服务器并 `docker compose up -d --force-recreate`。

### 环境变量

参考 `backend/.env.example`，生产环境需配置：

```bash
# Django
DJANGO_SECRET_KEY=<随机密钥>
DJANGO_DEBUG=False
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.com

# 数据库
DB_NAME=devtrack
DB_USER=postgres
DB_PASSWORD=<密码>
DB_HOST=<数据库主机>
DB_PORT=5432

# AI 服务
AI_API_KEY=<DeepSeek API Key>
AI_MODEL=deepseek-3.5-turbo

# GitHub
GITHUB_PAT=<GitHub Personal Access Token>
MATRIX_GITHUB_PAT=<组织级 GitHub PAT>

# MinIO 对象存储
MINIO_ENDPOINT=<MinIO 地址:端口>
MINIO_ACCESS_KEY=<Access Key>
MINIO_SECRET_KEY=<Secret Key>
MINIO_BUCKET=devtrack-uploads
MINIO_USE_SSL=False
MINIO_PUBLIC_URL=/uploads

# 仓库克隆目录
REPO_CLONE_DIR=/data/repos
```

### 外部依赖

| 服务 | 用途 | 初始化 |
|------|------|--------|
| PostgreSQL | 数据库 | 创建数据库，配置 `.env` |
| MinIO | 文件存储 | 运行 `scripts/minio-init.sh` |
| Traefik | 反向代理 | 配置外部网络 `traefik-network` |
| Watchtower | 自动更新 | 部署在同一 Docker 网络 |

### 首次部署清单

1. 准备 PostgreSQL 数据库
2. 配置 MinIO：`bash scripts/minio-init.sh <mc-alias>`
3. 创建部署目录，配置 `.env` 和 `docker-compose.yml`
4. 启动服务：`docker compose up -d`
5. 加载种子数据：`docker exec <backend> uv run python manage.py loaddata fixtures/ai_prompts.json`
6. 创建管理员：`docker exec -it <backend> uv run python manage.py createsuperuser`

## 测试

```bash
cd backend
uv run pytest                # 全部测试
uv run pytest -x             # 遇错即停
uv run pytest tests/test_issues.py::TestIssueAPI::test_create_issue -v  # 单个测试
```

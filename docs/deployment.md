# 部署与运维

## 依赖隔离与后端工具

Docker 部署不使用宿主机的 Node.js、npm 或 Python 环境：

- Web 在 Node.js 22 构建容器内执行 `npm ci`、测试和构建，生成的静态文件及浏览器模型由 Nginx 容器提供。最终 Web 镜像运行 Nginx，无需宿主机 Node/npm 或 `/tmp` 中的依赖。
- 浏览器 API 客户端默认访问同源 `/api`。容器内 Nginx 转发至 API，并支持 200 MiB 音频上传、流式进度和长任务；本地 Vite 开发及预览使用相同路径代理到 `127.0.0.1:8000`。
- API 镜像安装 FastAPI、数据库客户端和任务调度依赖；通过 Redis 将音频处理任务交给 Worker。
- Worker 镜像安装 FFmpeg（含 FFprobe）、libsndfile、OpenMP 运行库、Demucs 和 Basic Pitch 及其 Python 依赖。默认使用 PyTorch 官方 CPU 安装源，与当前未配置 GPU 的 Compose 服务一致；需要 GPU 时应调整 PyTorch 安装源和容器 GPU 配置。构建时检查工具版本和主要模块导入。
- API 与 Worker 共享 `app-data` 卷。Demucs 首次推理下载的权重写入 `model-cache` 卷，重建 Worker 后可复用；首次推理需要联网。

只构建后端镜像并检查工具，不启动或停止服务：

```bash
docker compose -f infra/compose.yaml build api worker
docker compose -f infra/compose.yaml run --rm --no-deps worker ffmpeg -version
docker compose -f infra/compose.yaml run --rm --no-deps worker python -c "from basic_pitch.inference import Model; import demucs.separate; print('model dependencies OK')"
```

首次构建需要下载音频处理和机器学习依赖，耗时及镜像体积会明显大于普通 API。`.dockerignore` 会排除宿主机的 `node_modules`、`.venv`、本地配置和音频数据，避免将这些文件发送到构建环境。若本地 API 已占用 8000 端口，应先停止该进程，再启动 Compose 的 API 服务。

## 启动前检查

生产环境应修改 Compose 中的数据库、MinIO 凭据，不把数据库和 Redis 端口暴露到公网，并在 Web/API 前配置 TLS 反向代理。应用数据位于 `app-data`，PostgreSQL 元数据位于 `postgres-data`；两者必须成组备份。

```bash
docker compose -f infra/compose.yaml config
docker compose -f infra/compose.yaml build api worker web
docker compose -f infra/compose.yaml up -d --wait web worker
curl --fail http://localhost:8888/api/health/ready
curl --fail http://localhost:8000/health/live
curl --fail http://localhost:8000/health/ready
```

API 启动时先执行 Alembic migration。`ready` 失败时不要继续切换流量，应先检查 API 日志、数据库连接和 Redis 健康状态。
Compose 会等待 API 和数据库健康后再启动 Web 与 Worker。此启动方式使用 PostgreSQL、Redis 和共享文件卷，不启动尚未接入应用的 MinIO 服务。默认 Web/API 端口仅绑定宿主机回环地址。

前端代码修改后运行 `docker compose -f infra/compose.yaml up -d --build --wait web`；日常启动不需要 `--build`。当前为静态文件服务模式，不提供热更新。本地开发的 SQLite 和 `data/` 文件不会自动迁入容器的数据卷，切换前应按需要迁移或保留本地数据。

## 备份与恢复

备份前短暂停止 API 和 Worker 写入，再导出数据库并备份应用数据卷：

```bash
docker compose -f infra/compose.yaml stop api worker
docker compose -f infra/compose.yaml exec -T postgres pg_dump -U vocal_score -Fc vocal_score > vocal-score.dump
docker run --rm -v vocal-score-studio_app-data:/source:ro -v "$PWD/backups:/backup" alpine tar czf /backup/app-data.tgz -C /source .
docker compose -f infra/compose.yaml start api worker
```

恢复到空环境时，先还原 `app-data`，再用 `pg_restore --clean --if-exists` 还原数据库，最后启动 API 与 Worker并检查 `/health/ready`。备份文件包含用户音频，必须加密、限制访问并按保留策略删除。

## 数据保留与删除

当前版本不自动删除项目。管理员应根据产品隐私承诺制定保留期；用户从“最近项目”执行删除时，API 会在同一操作中删除项目、关联任务、上传记录、源音频和任务工作目录。可通过以下请求核验删除结果：

```bash
curl -X DELETE http://localhost:8000/v1/projects/PROJECT_ID
curl --fail http://localhost:8000/v1/projects/PROJECT_ID
```

第二个请求应返回 404。数据库/数据卷备份中的副本会持续到备份保留期结束，因此用户说明中应明确这一点。

## 升级与回滚

升级前创建数据库和 `app-data` 备份，再构建带固定 Git 提交号的镜像。先运行 migration 和健康检查，再切换 Web 流量。代码回滚不能自动回滚数据库结构；若迁移不向后兼容，应恢复成组备份，而不是只降级镜像。

## 常见故障

- 任务长期停在 queued：检查 Redis、Celery Worker 日志和 `VSS_WORKER_BACKEND`。
- Worker OOM：降低并发、使用短音频验证，或部署更大内存/GPU；失败任务可从界面安全重试。
- FFmpeg 或模型不可用：确认 Worker 镜像构建完成并检查模型下载/许可要求。
- 磁盘持续增长：核对项目保留策略和 `app-data` 卷容量，先通过项目删除 API 清理，避免直接删除仍被数据库引用的文件。

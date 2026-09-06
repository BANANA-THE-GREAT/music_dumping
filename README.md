# 拾音 · Vocal Score Studio

输入常见音频，生成可演奏、可校正的主旋律简谱与五线谱，并导出 MIDI / MusicXML。

## 已实现

- 三种转录模式：浏览器本地 Basic Pitch、后端快速演示、后端 Demucs + Basic Pitch 高质量管线
- 上传、持久化任务、SSE 进度、取消和稳定错误状态
- 音频准备、人声分离、旋律转谱三条子任务进度，分别显示等待、处理、完成和失败；进度断线后刷新可恢复
- BPM、拍号、调性分析与服务端重新量化
- 五线谱 / 简谱切换、合成器演奏和音符跟随
- 简谱点击选音，方向键升降半音并自动保存 revision
- 服务端标准 MIDI / MusicXML 导出
- PostgreSQL / Redis / Celery 容器栈与 Alembic 数据库迁移

## 本地开发

需要 Node.js 20+ 和 Python 3.11/3.12。

```bash
npm install
python -m pip install -e ".[dev]"
npm run dev:api
npm run dev:web
```

浏览器访问 Vite 输出的地址。默认数据库和上传位于 `data/`；不安装模型依赖时请选择“后端演示”或“浏览器本地”。运行高质量 Worker 需额外安装：

```bash
python -m pip install -e ".[models]"
```

并确保 `ffmpeg` 在 PATH 中。

## 容器部署

宿主机只需要 Docker 和 Docker Compose，不需要安装或升级 Node.js、npm、Python、FFmpeg 或模型依赖。
前端在 Node.js 22 构建容器中安装 npm 依赖；音频处理工具和模型运行依赖安装在后端 Worker 镜像中，与宿主机的其他项目隔离。

```bash
docker compose -f infra/compose.yaml up -d --build --wait web worker
```

Web 默认位于 `http://localhost:8080`，API 位于 `http://localhost:8000`。API 容器启动前自动执行 Alembic migration。
浏览器通过同一站点的 `/api` 请求后端；上传、SSE 进度和导出均由 Nginx 转发。上述命令同时启动所需的 PostgreSQL、Redis 和 API，当前本地文件存储不需要 MinIO。
如果已经运行本地 API，需先释放其 8000 端口。高质量模式由 Worker 内的 FFmpeg、Demucs 和 Basic Pitch 执行；首次使用 Demucs 时会联网下载模型权重，后续复用 `model-cache` 数据卷。

日常启动和修改前端后重新构建：

```bash
docker compose -f infra/compose.yaml up -d --wait web worker
docker compose -f infra/compose.yaml up -d --build --wait web
```

前端采用构建后由 Nginx 提供静态文件的方式，修改源代码后需重新构建 Web 镜像；运行和构建均不依赖宿主机或 `/tmp` 中的 Node/npm。容器数据保存到 Docker 卷，与本地开发的 `data/` 目录独立。

生产部署、备份恢复、数据保留与故障排查见 [部署运维指南](docs/deployment.md)。

## 验证

```bash
python -m ruff check apps/api workers
python -m mypy apps/api/app workers/transcription/vss_worker
python -m pytest
npm test
npm run build
```

更多说明见 [架构](docs/architecture.md)、[API](docs/api.md)、[评测](docs/evaluation.md) 和 [模型许可](docs/model-licenses.md)。

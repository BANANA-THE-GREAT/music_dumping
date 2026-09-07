# Agent 工作约定

本文件适用于本仓库及其所有子目录中的 agent 工作。

## Docker 优先的开发与验证环境

- 本项目长期以 `infra/compose.yaml` 和 `infra/docker/` 中的镜像作为标准运行环境。不要因为宿主机缺少或版本较旧的 Node.js、npm、Python、FFmpeg、Basic Pitch、Demucs 或 PyTorch，就判断项目依赖缺失或验证不可执行；先检查 Docker 配置和现有容器。
- 开始环境诊断时优先运行 `docker compose -f infra/compose.yaml config`、`docker compose -f infra/compose.yaml ps -a` 和 `docker compose -f infra/compose.yaml images`。除非用户明确要求本地非容器开发，不要为迁就宿主机版本擅自修改 workspace、依赖或构建脚本。
- Web 构建镜像为 `node:22-alpine`，镜像构建阶段执行 `npm ci`、`npm test` 和 `npm run build`；最终由 `nginx:1.29-alpine` 提供静态文件。因此前端标准验证是 `docker compose -f infra/compose.yaml build web`，宿主机无需安装 Node.js 22。前端改动后使用 `docker compose -f infra/compose.yaml up -d --build --wait web` 更新运行服务。
- API 镜像为 `python:3.11-slim`，安装 `pyproject.toml` 的生产依赖，启动时先执行 Alembic migration，再运行 Uvicorn。API 默认映射到宿主机 `127.0.0.1:8000`。
- Worker 镜像为 `python:3.11-slim`，安装 FFmpeg/FFprobe、libsndfile、OpenMP、CPU 版 PyTorch 以及 `.[models]` 中的 Basic Pitch 和 Demucs。构建时已经检查 FFmpeg、FFprobe 和主要 Python 模块导入；运行时以 Celery 单并发执行任务。需要核验时使用：

```bash
docker compose -f infra/compose.yaml build api worker
docker compose -f infra/compose.yaml run --rm --no-deps worker ffmpeg -version
docker compose -f infra/compose.yaml run --rm --no-deps worker python -c "from basic_pitch.inference import Model; import demucs.separate; print('model dependencies OK')"
```

- 默认 Compose Worker 使用 CPU PyTorch。GPU 模式通过叠加 `infra/compose.gpu.yaml` 构建 CUDA PyTorch 并申请可见 GPU，设备由 `VSS_INFERENCE_DEVICE=auto|cpu|cuda` 控制；宿主机仍须预先安装并配置 NVIDIA Container Toolkit。宿主机存在 NVIDIA GPU 不代表容器已经使用 GPU，启动后必须在容器内检查 `torch.cuda.is_available()`。
- GAME + torchcrepe 不进入默认 Worker；显式实验模式使用 `scripts/build-quality-worker.sh` 构建。脚本保留独立的 `vocal-score-studio-worker-basic:latest` 基础标签，校验固定源码归档和 `data/models/game/GAME-1.0-medium/model.pt` 的 SHA-256，再生成 `vocal-score-studio-worker:latest`。启动时必须沿用同一 Dockerfile 选择：

```bash
scripts/build-quality-worker.sh
VSS_WORKER_DOCKERFILE=infra/docker/Dockerfile.worker-quality \
  docker compose -f infra/compose.yaml up -d --wait worker
scripts/run-quality-segmentation-smoke.sh
```

GPU quality Worker 使用 `scripts/build-quality-worker-gpu.sh` 构建，并以 `VSS_WORKER_DOCKERFILE=infra/docker/Dockerfile.worker-quality docker compose -f infra/compose.yaml -f infra/compose.gpu.yaml up -d --no-build --wait worker` 启动。不要把 GPU override 合并进默认 Compose，也不要在未验证 CUDA 可用时删除 CPU 回退路径。

宿主机缺少 NVIDIA Container Toolkit 时，使用 `scripts/setup-nvidia-container-toolkit.sh` 安装并配置 Docker runtime；该脚本需要 sudo 密码且会重启 Docker。重启后先运行 `docker run --rm --gpus all vocal-score-studio-worker:latest python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"`，通过后才能切换 GPU Worker。

- GAME 权重通过 `../data/models/game:/models/game:ro` 只读挂载，不在 Docker build context 内。quality Worker 仍保留 Basic Pitch 回退；默认 Compose 未构建 quality Worker 时，实验任务必须明确失败为 `EXPERIMENTAL_ENGINE_NOT_CONFIGURED`，不得静默改用其他模型。模型运行验证优先检查 F0 JSONL、项目 provenance、pending 边界建议和子进程取消，不要把建议自动应用到项目音符。
- API 与 Worker 共享 `app-data` 卷；Demucs 等下载缓存位于 `model-cache` 卷，重建 Worker 不应默认删除这些卷。PostgreSQL 和 Redis 分别使用持久化卷。MinIO 当前在 Compose 中定义但不属于常规 `up -d --wait web worker` 启动链路，不要无故启动或依赖它。
- 常规启动命令为 `docker compose -f infra/compose.yaml up -d --build --wait web worker`，浏览器入口为 `http://localhost:8888`。Nginx 将同源 `/api` 转发到 API；不要因宿主机直连方式不同而改写前端默认 API 路径。
- Python 的 Ruff、mypy、pytest 属于开发依赖，不在精简的 API/Worker 运行镜像中。宿主机 `.venv` 可用时可直接运行；需要完全隔离验证时，可在重新构建 API 镜像后使用一次性容器安装开发额外依赖再执行检查。无论使用哪种方式，都要说明验证发生在宿主机还是容器内。
- `.dockerignore` 明确排除宿主机的 `.venv`、`node_modules`、构建产物、模型、音频和运行数据。不要假设镜像会复用这些宿主机目录，也不要为加快构建而把模型权重或用户数据加入构建上下文。
- 外部依赖、模型权重或数据集的下载链接无法联通，或下载速度慢到明显阻塞工作时，可以停止反复重试，向用户说明目标文件、来源、期望路径和校验信息，请用户自行设法下载后再继续。

## 项目用途与第三方许可

- 本项目按作者的非商业用途维护，计划在 GitHub 公开源代码，不计划用于商业化或收费服务。后续技术选型应以此为前提，不得擅自将项目转为商业用途。
- 允许评估符合上述用途的非商用模型，但必须分别核对代码、模型权重和数据集的许可证；“在 GitHub 开源”不代表可以忽略非商用、署名、相同方式共享或再分发限制。
- 本条是项目用途和开发约定，不修改根目录 `LICENSE`，也不替换第三方授权。任何许可证变更、商业化或另行授权需求，必须先向用户说明并取得明确指示。
- 每引入或计划采用一个第三方开源项目，必须在根目录 `README.md` 明确列出名称、官方链接、用途、接入状态和已知许可限制，并同步维护 `docs/model-licenses.md`。候选工具不能写成已接入功能；未核实的许可必须标为待核实。
- 集成前记录上游版本或 commit、权重下载来源、SHA-256、代码许可、权重许可和已知数据限制。保留必要的版权及署名说明；修改和再分发衍生权重前单独核查相同方式共享义务。
- 不向 Git 仓库提交模型权重、未经授权的歌曲、人声 stem 或私有标注。模型优先通过官方链接和可校验的下载脚本获取；测试数据只有确认允许公开再分发后才能提交。
- 新的专项实施计划放在 `plan/`，明确待办、验收标准、风险和回退方案；没有实测证据不得把模型宣传指标写成本项目已达到的效果。

## 阶段性完成后自动提交

- 每完成一个可独立说明、验证和回退的阶段性功能或变更，agent 必须自行创建一个 Git commit。功能开发、缺陷修复、重构、配置调整和文档更新均适用。
- 在进入下一阶段或向用户报告本阶段完成之前，完成相关验证、检查差异并提交，不要将已完成阶段的改动一直留在工作区。
- 创建本地 commit 无需再次请求用户确认；用户明确要求暂不提交时，以用户指令为准。
- 提交前运行与本次改动相关的必要检查，例如测试、类型检查、构建或配置校验。若验证失败，应先修复；若受环境或权限限制无法完成验证或提交，应明确报告原因，不得声称已完成。
- 每个 commit 只包含当前阶段相关的改动。提交前检查 `git status`、工作区差异和暂存区差异，按文件路径暂存，保留用户及其他任务的无关改动。
- 提交信息遵循 Conventional Commits，简洁描述实际变更，例如 `feat(editor): support note splitting`、`fix(api): handle revision conflicts` 或 `docs(agents): define milestone commit workflow`。
- 不提交用户音频、模型权重、凭据、数据库、依赖目录或构建产物。
- 默认只创建本地 commit。推送远端、合并分支或重写已有提交历史，需要用户另行授权。
- 阶段交付说明应包含已完成的内容、验证结果，以及 commit 的短哈希和提交信息。没有文件变更的问答或检查不创建空提交。

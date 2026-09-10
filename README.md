# 拾音 · Vocal Score Studio

输入常见音频，生成可演奏、可校正的主旋律简谱与五线谱，并导出 MIDI / MusicXML。

## 项目定位与实施计划

本项目以个人学习、研究和非商业使用为目的，计划在 GitHub 公开源代码，不计划用于商业化或收费服务。
这是一项项目用途约定，源码授权仍以根目录 [LICENSE](LICENSE) 为准；第三方代码、模型权重及数据分别遵循各自许可证，不能因为本仓库公开就视为全部可自由再分发。

当前人声分离链路保留 Demucs。下一轮重点是减少转录和量化的信息损失、评测歌声专用 MIDI 模型，以及用连续音高校验候选音符。
详细步骤见 [人声转 MIDI 质量升级实施计划](plan/vocal-to-midi-quality.md)。根目录 [PLAN.md](PLAN.md) 保留为早期架构规划，不代表本轮待办或全部已实现功能。

## 使用及拟采用的开源项目

| 项目 | 状态与用途 | 许可及接入注意事项 |
|---|---|---|
| [Demucs](https://github.com/facebookresearch/demucs) | 已接入：人声分离，继续保留 | 固定所用版本、权重及其许可，见许可清单 |
| [Basic Pitch](https://github.com/spotify/basic-pitch) / [Basic Pitch TS](https://github.com/spotify/basic-pitch-ts) | 已接入：后端及浏览器转录；保留为评测和回退基线 | Python 项目代码为 Apache-2.0；TS 版本及具体权重另行核对 |
| [abcjs](https://github.com/paulrosen/abcjs) | 已接入：五线谱渲染 | 具体版本许可及第三方声明见许可清单 |
| [Verovio](https://github.com/rism-digital/verovio) | 已接入独立渲染容器：将 MusicXML 刻制为五线谱 SVG，并用于 PNG/PDF 导出 | 固定 Python 包 `6.2.1`；LGPL，容器分发时保留许可证与上游说明 |
| [Inkscape](https://inkscape.org/) | 已接入独立渲染容器：将服务端 SVG 转换为 144 DPI PNG 或 PDF | GPL；只作为独立命令行程序运行，生成文件的权利不因运行 Inkscape 自动改变 |
| [Noto CJK](https://github.com/notofonts/noto-cjk) | 已接入渲染容器：中文谱名的本地字体回退，不依赖 Google Fonts | SIL Open Font License 1.1；分发字体时保留版权和许可文本 |
| [OpenSheetMusicDisplay](https://github.com/opensheetmusicdisplay/opensheetmusicdisplay) | 候选：浏览器五线谱和简谱对照，尚未接入 | 本体 BSD-3-Clause；Jianpu Display 仍标为 early access/sponsor 功能，需单独确认可用性和授权 |
| [MuseScore Studio](https://musescore.org/) / [LilyPond](https://lilypond.org/) | 候选：出版级离线五线谱对照或回退，尚未接入 | 镜像体积、无头运行和 GPL 边界需在真正接入前单独验证 |
| [GAME](https://github.com/openvpi/GAME) | 已接入显式可选的 quality Worker，medium 生成实验音符候选；默认仍为 Basic Pitch | 代码 MIT；[官方 1.0 权重](https://github.com/openvpi/GAME/releases/tag/v1.0.0)为 CC BY-NC-SA 4.0，须遵守非商用、署名及适用的相同方式共享条件；权重只读挂载，不进入镜像 |
| [SOME](https://github.com/openvpi/SOME) | 已完成 P1 独立 CPU 对照；未达到预登记门槛，未接入默认 Worker | 代码 MIT；[官方基线权重](https://github.com/openvpi/SOME/releases/tag/v1.0.0-baseline)为 CC BY-NC-SA 4.0 |
| [ROSVOT](https://github.com/RickyL-2000/ROSVOT) | 备选：中文、分离残留较重的歌声转录，按评测需要引入 | 代码 MIT；具体权重授权和数据限制仍需核实，不能由代码许可证推断 |
| [RMVPE](https://github.com/Dream-High/RMVPE) / [部署实现](https://github.com/yxlllc/RMVPE) | 暂停：原始代码可用，但常用部署权重授权不明确 | 原始代码 Apache-2.0；部署仓库及 `230917` 权重未提供明确 LICENSE，不接入或再分发 |
| [torchcrepe](https://github.com/maxrmorrison/torchcrepe) | 已接入可选 quality Worker，保存 10ms F0 证据并生成默认不采用的止音建议 | 固定 `0.0.24` / commit `19e2ec3d494c0797a5ff2a11408ec5838fba6681`；仓库 MIT，包内权重由原始 CREPE 权重转换。full 权重哈希见许可清单 |
| [DDSP](https://github.com/magenta/ddsp) | 远期可选：谐波重合成和频谱对照实验，不是本轮默认依赖 | 选型时核对代码、预训练模型及数据许可；不是开箱即用的人声转 MIDI 工具 |
| [Vocadito](https://zenodo.org/records/5578807) | 已用于 P0：孤立人声 Basic Pitch 基线、双标注一致性和损失定位 | Bittner 等人，DOI `10.5281/zenodo.5578807`，数据集 CC BY 4.0；音频及转换标注保存在 Git 忽略的 `data/`，仓库只提交可复现 manifest 和汇总报告 |

上述候选来自官方资料调研，不代表已安装、已验证效果或已经选为默认引擎。非商业用途不能代替许可审查；完整登记和分发规则见 [模型与依赖许可清单](docs/model-licenses.md)。

## 已实现

- 三种转录模式：浏览器本地 Basic Pitch、后端快速演示、后端 Demucs + Basic Pitch 高质量管线
- 显式实验模式：可选 quality Worker 运行 GAME + torchcrepe，并逐条接受、忽略或撤销 F0 止音建议
- 上传、持久化任务、SSE 进度、取消和稳定错误状态
- 音频准备、人声分离、旋律转谱三条子任务进度，分别显示等待、处理、完成和失败；进度断线后刷新可恢复
- BPM、拍号、调性分析与服务端重新量化
- 五线谱 / 简谱切换、合成器演奏和音符跟随
- 简谱点击选音，方向键升降半音并自动保存 revision
- 服务端标准 MIDI / MusicXML 导出
- 服务端谱面版五线谱与简谱 SVG/PNG/PDF 导出；五线谱使用 Verovio，简谱使用稳定音符 ID 的项目内 SVG 布局器
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

API 与 Worker 使用固定的 Python `3.11.16` / Debian trixie 依赖基础镜像。`requirements/api.lock` 和
`requirements/worker.lock` 固定已经验证的 Python 依赖；业务代码镜像只安装项目自身，
不会因为修改 Python 源码而重新下载整套依赖。使用以下入口构建：

```bash
make build-api
make build-worker
make build-renderer
```

构建脚本根据锁文件、依赖 Dockerfile 和 PyTorch 配置计算基础镜像标签。本地已有对应标签时直接复用；
只有首次构建、锁文件变化或 Python/PyTorch/系统依赖变化时才构建依赖层，此时可能需要联网。

谱面图片由内部 `renderer` 服务生成。该容器固定安装 Verovio `6.2.1`、Inkscape 和
Noto CJK 字体；API 不在请求期间下载渲染器或字体。首次执行 `make build-renderer` 需要联网，
后续普通启动和业务代码更新复用本地镜像。

如果 Docker Hub 的基础镜像元数据请求失败，但本机已经构建过 API 依赖镜像，可以跳过
Docker Hub，复用同一 Python 3.11/Trixie 基础层：

```bash
VSS_RENDERER_BASE_IMAGE=vocal-score-studio-api-deps:local make build-renderer
```

该方式仍需要 Debian 软件源和 PyPI 下载 Inkscape、Noto CJK 与 Verovio，但不会访问
`registry-1.docker.io` 获取 Python 基础镜像。

如果 `deb.debian.org` 在当前网络中超时，可以同时指定 Debian 镜像。Dockerfile 使用
BuildKit 的 apt/pip 缓存挂载，网络中断后重试会复用已经下载的包：

```bash
VSS_RENDERER_BASE_IMAGE=vocal-score-studio-api-deps:local \
VSS_DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian \
VSS_DEBIAN_SECURITY_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian-security \
make build-renderer
```

`make build-renderer` 默认使用以上 Debian 镜像，并显式传递 Docker build args。Inkscape
与 Noto CJK 字体分层安装；网络中断后重复执行命令会复用已经成功完成的构建层。

renderer 启动后可运行约 1、10、50 页的 SVG/PNG/PDF 基准：

```bash
make benchmark-renderer
```

基准输出 JSONL，包含实际页数、耗时、文件大小及容器 cgroup 内存变化。

前端构建后可打开 `http://localhost:8888/score-rendering-comparison.html`，选择一份已保存
谱面，并排检查当前交互编辑器与导出简谱 SVG。该诊断页也支持
`?project=<project_id>` 直接定位谱面。

```bash
docker compose -f infra/compose.yaml up -d --wait web worker
```

Web 默认位于 `http://localhost:8888`，API 位于 `http://localhost:8000`。API 容器启动前自动执行 Alembic migration。
浏览器通过同一站点的 `/api` 请求后端；上传、SSE 进度和导出均由 Nginx 转发。上述命令同时启动所需的 PostgreSQL、Redis 和 API，当前本地文件存储不需要 MinIO。
如果已经运行本地 API，需先释放其 8000 端口。高质量模式由 Worker 内的 FFmpeg、Demucs 和 Basic Pitch 执行；首次使用 Demucs 时会联网下载模型权重，后续复用 `model-cache` 数据卷。

实验 GAME + torchcrepe 引擎使用单独的 quality Worker。先把官方 GAME medium 的
`model.pt` 放在 `data/models/game/GAME-1.0-medium/model.pt`，再执行：

```bash
scripts/build-quality-worker.sh
VSS_WORKER_DOCKERFILE=infra/docker/Dockerfile.worker-quality \
  docker compose -f infra/compose.yaml up -d --wait worker
```

构建脚本固定并校验源码与权重哈希。quality Worker 仍支持 Basic Pitch；实验引擎只有在任务中显式选择 `game_f0` 时运行。标准 Worker 收到该选项会返回 `EXPERIMENTAL_ENGINE_NOT_CONFIGURED`，不会回退成假结果或 Basic Pitch。GAME 原始音符、独立 F0 文件和边界建议会分别保存，建议默认保持 pending，不自动改写谱面。钢琴卷帘可叠加有声 F0 和建议前后边界；接受、忽略及撤销均保存 revision，撤销不会覆盖接受后发生的其他时值编辑。

项目同时保存独立的演唱版 `performance_notes` 和谱面版 `notes`。重新量化始终从演唱版的毫秒级时间重建谱面版，不在已有量化结果上累积舍入误差；MIDI 导出可选择谱面版或演唱版，演唱版支持可选的 cents pitch bend，MusicXML 固定使用谱面版。旧 `1.0` 项目缺少演唱版字段时会从现有音符兼容补齐。

谱面量化可以关闭，并支持直拍、三连音/六连音网格、0–100% 吸附强度和毫秒级节拍偏移。量化配置与同起点冲突保存在项目中；冲突音符会全部保留并在界面提示，不会静默删除置信度较低的候选。

钢琴卷帘以轮廓显示演唱版真实时间、以实心块显示谱面版量化时间，并继续叠加 F0 与边界证据；同起点冲突会高亮。合成试听可以在演唱版真实时值和谱面版量化时值之间切换。

P5.1 提供独立的简单谐波诊断试听：`python scripts/synthesize-harmonic.py f0.jsonl harmonic.wav --report harmonic.json`。该工具只根据 F0 和 periodicity 生成 WAV，用于听辨音高、发声区间和边界，不改变默认转录链路。`scripts/evaluate-f0-alignment.py` 可在固定范围内检查统一延迟，但不做时间拉伸。

浏览器端到端验收使用固定版本的 Playwright `1.55.0` 和 Chromium 镜像 `mcr.microsoft.com/playwright:v1.55.0-noble`，不进入生产 Nginx 镜像。启动 Compose 服务后运行 `scripts/run-browser-checks.sh`；可用 `SCORE_URL` 覆盖测试地址。

NVIDIA GPU 为可选运行模式，不改变默认 CPU Compose。宿主机完成 NVIDIA Container Toolkit 配置后，普通 Worker 可执行：

```bash
scripts/setup-nvidia-container-toolkit.sh
docker run --rm --gpus all vocal-score-studio-worker:latest \
  python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
make build-worker-gpu
docker compose -f infra/compose.yaml -f infra/compose.gpu.yaml up -d --no-build --wait worker
docker compose -f infra/compose.yaml -f infra/compose.gpu.yaml exec worker \
  python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

实验 GPU Worker 使用 `scripts/build-quality-worker-gpu.sh` 构建，然后执行：

```bash
VSS_WORKER_DOCKERFILE=infra/docker/Dockerfile.worker-quality \
  docker compose -f infra/compose.yaml -f infra/compose.gpu.yaml \
  up -d --no-build --wait worker
```

GPU 镜像默认使用 PyTorch `2.8.0+cu128` wheel，可通过 `VSS_PYTORCH_INDEX_URL` 和 `VSS_PYTORCH_PACKAGE` 覆盖。构建过程会检查 `torch.version.cuda`，避免误装 CPU wheel。运行时 `VSS_INFERENCE_DEVICE` 支持 `auto`、`cpu`、`cuda`，默认以 `VSS_CUDA_VISIBLE_DEVICES=0` 只使用一张卡；显式选择 `cuda` 但容器不可用时任务会失败，不会静默回退 CPU。Demucs、GAME 和 torchcrepe 使用同一选择结果。

GPU override 默认设置 `HF_HUB_OFFLINE=1`，让 Demucs 直接读取 `model-cache`，避免每个任务等待 Hugging Face 远端元数据检查。全新环境首次下载 Demucs 权重时，临时在启动命令前设置 `VSS_HF_HUB_OFFLINE=0`；权重缓存完成后恢复默认离线模式。

日常启动和修改前端后的命令：

```bash
docker compose -f infra/compose.yaml up -d --wait web worker
docker compose -f infra/compose.yaml build web
docker compose -f infra/compose.yaml up -d --wait web
make build-api
docker compose -f infra/compose.yaml up -d --no-build --wait api
```

没有修改镜像相关代码时只执行第一条；`build web` 只在前端源码、依赖或 Dockerfile 变化后执行。
后端源码变化使用 `make build-api`，它会复用固定依赖镜像；不要使用 `--no-cache`，也不要删除
`vocal-score-studio-api-deps:*`、`vocal-score-studio-worker-deps:*` 或模型缓存来解决普通代码更新。

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

P0、P1、P1.5 与 P3 F0 诊断已经完成。GAME medium 单独使用时未通过全部门槛；固定的 GAME + torchcrepe F0 边界规则在未访问 holdout 上通过预登记质量门槛，但仍有逐片段回退、CPU 成本和取消问题，因此默认引擎保持 Basic Pitch。结果见 [Basic Pitch 基线](evaluation/reports/vocadito-baseline.md)、[候选模型对比](evaluation/reports/vocadito-candidate-comparison.md)、[GAME tuning](evaluation/reports/vocadito-game-tuning.md)和[F0 边界诊断](evaluation/reports/vocadito-f0-boundary-comparison.md)；真实混音与 Demucs 残留样本仍待补充。运行方法、固定容差和标注要求见[转录质量评测](docs/evaluation.md)与[人声转录标注规范](docs/transcription-annotation.md)。

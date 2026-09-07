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
| [GAME](https://github.com/openvpi/GAME) | 已完成 P1 独立容器评测，medium 为最佳实验候选；未接入默认 Worker | 代码 MIT；[官方 1.0 权重](https://github.com/openvpi/GAME/releases/tag/v1.0.0)为 CC BY-NC-SA 4.0，须遵守非商用、署名及适用的相同方式共享条件 |
| [SOME](https://github.com/openvpi/SOME) | 已完成 P1 独立 CPU 对照；未达到预登记门槛，未接入默认 Worker | 代码 MIT；[官方基线权重](https://github.com/openvpi/SOME/releases/tag/v1.0.0-baseline)为 CC BY-NC-SA 4.0 |
| [ROSVOT](https://github.com/RickyL-2000/ROSVOT) | 备选：中文、分离残留较重的歌声转录，按评测需要引入 | 代码 MIT；具体权重授权和数据限制仍需核实，不能由代码许可证推断 |
| [RMVPE](https://github.com/Dream-High/RMVPE) / [部署实现](https://github.com/yxlllc/RMVPE) | 拟引入：连续基频和发声区间校验，不单独代替音符切分 | 最终采用的实现、版本、权重来源与授权均需确认 |
| [DDSP](https://github.com/magenta/ddsp) | 远期可选：谐波重合成和频谱对照实验，不是本轮默认依赖 | 选型时核对代码、预训练模型及数据许可；不是开箱即用的人声转 MIDI 工具 |
| [Vocadito](https://zenodo.org/records/5578807) | 已用于 P0：孤立人声 Basic Pitch 基线、双标注一致性和损失定位 | Bittner 等人，DOI `10.5281/zenodo.5578807`，数据集 CC BY 4.0；音频及转换标注保存在 Git 忽略的 `data/`，仓库只提交可复现 manifest 和汇总报告 |

上述候选来自官方资料调研，不代表已安装、已验证效果或已经选为默认引擎。非商业用途不能代替许可审查；完整登记和分发规则见 [模型与依赖许可清单](docs/model-licenses.md)。

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

P0 基线与 P1 GAME/SOME 对比已经完成。GAME medium 在 Vocadito holdout 上最好，但没有候选通过全部预登记门槛，默认引擎保持 Basic Pitch。结果见 [Basic Pitch 基线](evaluation/reports/vocadito-baseline.md)和[候选模型对比](evaluation/reports/vocadito-candidate-comparison.md)；真实混音与 Demucs 残留样本仍待补充。运行方法、固定容差和标注要求见[转录质量评测](docs/evaluation.md)与[人声转录标注规范](docs/transcription-annotation.md)。

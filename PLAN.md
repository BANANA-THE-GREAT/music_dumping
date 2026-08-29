# 拾音（Vocal Score Studio）前后端分离升级计划

## 1. 目标与范围

把当前浏览器单体原型升级为可持续开发的完整应用：前端负责上传、任务状态、谱面编辑与播放；后端负责音频标准化、人声分离、节拍/拍号/调性分析、旋律转录、后处理和导出；Git 管理全部源码、协议与测试，但不提交模型、构建产物、用户音频和运行数据。

第一阶段产品边界：优先支持流行歌曲中的单一主唱，输出可编辑的主旋律简谱/五线谱、MIDI 与 MusicXML。多乐器总谱、移动端原生应用和实时跟唱不进入首个后端版本。

## 2. 当前基线

- Vite + TypeScript 单页应用，UI、Basic Pitch 推理、轻量中心声像人声提取、BPM/拍号/调性分析均在浏览器中。
- 已支持简谱/五线谱、播放、MIDI/MusicXML 导出和 6 项单元测试。
- 当前没有 Git 仓库；`node_modules/`、`dist/`、模型二进制和测试音频均在工作目录中。
- 当前拍号只支持 3/4 与 4/4，人声分离不是真正的神经网络分轨，缺少可恢复的任务队列、持久化项目和谱面编辑器。

## 3. 关键技术决策

### 3.1 仓库与应用结构

采用单仓库 monorepo，避免前后端协议在多个仓库漂移：

```text
music_dumping/
├─ apps/
│  ├─ web/                 # Vite + React + TypeScript
│  └─ api/                 # FastAPI，仅处理 HTTP/WebSocket 与持久化
├─ workers/
│  └─ transcription/       # Python 推理 Worker，CPU/GPU 独立运行
├─ packages/
│  ├─ contracts/           # OpenAPI 生成的 TS 类型、JSON Schema
│  ├─ score-core/          # 前端乐谱模型、量化与编辑命令
│  └─ test-fixtures/       # 小型、可再分发的测试素材及标注
├─ infra/
│  ├─ docker/              # API/Worker 镜像
│  └─ compose.yaml         # PostgreSQL、Redis、MinIO、API、Worker
├─ docs/
│  ├─ architecture.md
│  ├─ api.md
│  ├─ model-licenses.md
│  └─ adr/                 # Architecture Decision Records
├─ scripts/
├─ .github/workflows/
├─ pyproject.toml
├─ package.json
└─ README.md
```

前端迁移到 React，但保留现有 `abcjs`、简谱渲染逻辑与 TypeScript 乐谱核心。采用 React 的原因是后续波形、钢琴卷帘、属性面板、撤销/重做和异步任务状态会形成复杂共享状态；不在迁移阶段更换刻谱引擎。

### 3.2 后端与任务系统

- API：Python 3.11 + FastAPI + Pydantic。
- 持久化：PostgreSQL；开发环境允许 SQLite 仅用于快速 API 测试。
- 队列：Celery + Redis。模型推理是长时间 CPU/GPU 计算，不放进 FastAPI `BackgroundTasks`。FastAPI 官方文档也建议重计算使用独立队列/进程。
- 文件存储：本地文件适配器和 S3 兼容适配器；开发环境使用 MinIO。数据库只保存元数据与对象键。
- 进度：Worker 写 Redis/数据库，前端优先使用 Server-Sent Events；SSE 不可用时退化为 2 秒轮询。
- 模型生命周期：Worker 启动时加载模型并复用，任务之间不重复加载；CPU 与 GPU Worker 使用不同队列。

### 3.3 推理流水线

```text
上传 → 校验/指纹 → FFmpeg 标准化
     → Demucs 人声分离
     → Beat This! 节拍/下拍
     → Basic Pitch 人声音符
     → 调性/拍号/速度图分析
     → 单旋律路径选择与碎音清理
     → 节奏量化/小节化
     → ScoreProject JSON
     → MIDI / MusicXML / 预览音频
```

- 人声分离：先以 Demucs `htdemucs` 建立基线，但把分离器封装成 `Separator` 接口。原仓库维护状态和模型许可必须记录在 `model-licenses.md`，并保留替换 MDX/Roformer 的能力。
- 节拍与下拍：Beat This! 作为候选基线，模型与代码为 MIT；上线前仍需完成训练数据风险审查。
- 音符转录：后端 Python Basic Pitch 作为首个基线；保留模型适配器，后续可加入专用 vocal 模型做 A/B 评测。
- 调性：Krumhansl-Schmuckler + 音符时值直方图；再结合旋律收束音、强拍音提高稳定性。
- 拍号：从下拍间隔和重音模式判断 2/4、3/4、4/4、6/8，低置信度时要求用户确认；变拍子延后到第二阶段。
- 主旋律后处理：使用动态规划选择单音路径，代价包含置信度、音域、跳进、音符重叠、短音和音高连续性；保留原始音符以支持重新量化。

所有模型步骤必须输出版本、参数、耗时、设备、置信度和中间产物键，确保结果可复现。

## 4. 核心数据模型

`ScoreProject` 是前后端唯一权威格式，MusicXML 只是导出格式：

```ts
interface ScoreProject {
  schemaVersion: "1.0";
  projectId: string;
  source: { fileName: string; durationMs: number; audioObjectKey: string };
  analysis: {
    tempoMap: Array<{ timeMs: number; bpm: number }>;
    meterMap: Array<{ beat: number; numerator: number; denominator: number }>;
    keyMap: Array<{ beat: number; tonic: number; mode: "major" | "minor" }>;
    confidence: Record<string, number>;
  };
  notes: Array<{
    id: string;
    sourceStartMs: number;
    sourceEndMs: number;
    pitchMidi: number;
    confidence: number;
    quantizedStart: number;
    quantizedDuration: number;
    origin: "model" | "user";
  }>;
  pipeline: Array<{ stage: string; version: string; parameters: unknown }>;
  revision: number;
}
```

必须同时保留原始秒级时间和量化拍点。用户修改 BPM、拍号或量化精度时，从原始时间重新计算，不能累积量化误差。

## 5. API v1

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/v1/uploads` | 分片或普通上传，返回 `upload_id` |
| `POST` | `/v1/jobs` | 使用上传文件创建转录任务，返回 202 |
| `GET` | `/v1/jobs/{id}` | 任务状态、阶段、进度、错误码 |
| `GET` | `/v1/jobs/{id}/events` | SSE 进度与日志摘要 |
| `POST` | `/v1/jobs/{id}/cancel` | 请求取消尚未结束的任务 |
| `GET` | `/v1/projects/{id}` | 获取 `ScoreProject` |
| `PATCH` | `/v1/projects/{id}` | 基于 revision 的乐谱修改与冲突检查 |
| `POST` | `/v1/projects/{id}/requantize` | 修改 BPM/拍号/量化参数后重算 |
| `POST` | `/v1/projects/{id}/exports` | 创建 MIDI/MusicXML/PDF/音频导出 |
| `GET` | `/v1/exports/{id}` | 获取导出状态及短期下载地址 |
| `GET` | `/health/live` | 进程存活 |
| `GET` | `/health/ready` | 数据库、Redis、模型可用性 |

任务状态机：`queued → preprocessing → separating → tracking_beats → transcribing → postprocessing → rendering → completed`；任意运行态可进入 `failed` 或 `cancelling → cancelled`。错误响应必须包含稳定错误码、可读信息和是否可重试。

## 6. 前端产品计划

### 6.1 上传与任务页

- 文件类型、大小、时长预检；显示隐私说明和预计处理时间。
- 分阶段进度、取消、失败重试、刷新后恢复任务。
- 原曲、人声 stem 和转录试听切换。

### 6.2 校对工作台

- 顶部：播放、循环、节拍器、调速、原曲/stem/合成谱混音。
- 中部：波形 + 音高轮廓 + 钢琴卷帘，可拖动音高、起点和终点。
- 下部：五线谱/简谱切换，点击音符与时间轴双向定位。
- 右侧：BPM、拍号、调性、量化强度、音符属性及置信度。
- 命令式编辑模型：新增、删除、移动、缩放、拆分、合并；所有操作支持撤销/重做。
- 自动保存和 revision 冲突保护。

### 6.3 导出

- MIDI、MusicXML 为首要格式；PDF 通过 MuseScore/LilyPond 后端渲染作为后续增量。
- 导出前提供标题、作者、移调、速度、是否带歌词等选项。

## 7. Git 与协作规范

### 7.1 初始化

在第一个迁移提交前：

1. 创建 `.gitignore`，至少忽略 `node_modules/`、`dist/`、`.venv/`、`__pycache__/`、`.pytest_cache/`、模型权重、上传音频、stem、数据库和对象存储数据。
2. 创建 `.gitattributes`，统一 LF；图片和小型测试音频声明为 binary。
3. 模型不使用 Git LFS，改由带 SHA-256 校验的下载脚本管理；只有可合法再分发且足够小的测试 fixture 才进入仓库。
4. `git init -b main`，以当前可运行应用做 `chore: import browser prototype` 基线提交。
5. 第二个提交只做目录迁移，不混入行为改动，便于追踪历史。

### 7.2 分支与提交

- `main` 始终可构建；功能分支命名 `feat/...`、`fix/...`、`chore/...`。
- 使用短生命周期分支和 Pull Request，不建立长期 `develop` 分支。
- Conventional Commits：`feat(api): add transcription job endpoint`。
- PR 尽量小于 500 行有效改动；模型接入可拆为接口、实现、fixture、评测四个 PR。
- 合并使用 squash；发布版本打 `v0.x.y` / `v1.0.0` 标签并生成 changelog。
- `main` 开启保护：CI 必须通过、至少一次审查、禁止 force push。

### 7.3 CI 门禁

每个 PR 必须运行：

- 前端：TypeScript、ESLint、Vitest、生产构建、Playwright 核心流程。
- 后端：Ruff、mypy、pytest、OpenAPI schema 快照。
- 集成：Docker Compose 启动、上传 fixture、完成任务、校验 ScoreProject/MIDI/MusicXML。
- 安全：依赖漏洞扫描、secret scan、容器镜像扫描。
- 许可：模型及 Python/npm 依赖许可证清单变化检查。

GPU 模型回归测试放在定时或手动 workflow，不阻塞每个普通 PR；每次发布必须通过固定评测集。

## 8. 测试与质量指标

### 8.1 测试层级

- 单元测试：量化、调性、拍号、主旋律路径、编辑命令、导出。
- 契约测试：OpenAPI 与生成的 TypeScript client 同步。
- 集成测试：API + Redis + Worker + 存储，模型可用轻量 fake adapter。
- 模型回归：10–30 秒人工标注片段，覆盖清唱、流行混音、男女声、混响、3/4、4/4、6/8。
- E2E：上传、进度、编辑一个音符、保存、导出、刷新恢复。

### 8.2 发布门槛

- 音符 onset/pitch F1、raw pitch accuracy、beat F-measure、downbeat F-measure。
- BPM 容许半倍/双倍归一后的准确率；拍号准确率；调性准确率。
- 端到端成功率、P50/P95 处理耗时、GPU/CPU 峰值内存。
- 人工指标：生成谱“无需修改、少量修改、大量修改、不可用”的比例。

首个 Beta 的建议门槛：固定评测集任务成功率 ≥ 95%；30 秒音频在目标 GPU 上 P95 ≤ 60 秒；单旋律音符 F1 相对当前浏览器基线提升 ≥ 15%；所有失败都有稳定错误码且可以安全重试。

## 9. 分阶段实施与验收

### Phase 0：Git 基线与工程骨架（2–3 天）

- 初始化 Git、忽略规则、许可证、贡献指南和 ADR 模板。
- 将现有应用原样迁入 `apps/web`；恢复 dev 热更新命令。
- 建立 npm workspace、Python `uv`/`pyproject.toml`、基础 CI。

验收：全新 clone 后，一条命令安装并启动现有功能；仓库中无构建产物、模型和用户数据；CI 绿色。

### Phase 1：API 垂直切片（4–6 天）

- FastAPI、数据库迁移、上传、Job/Project schema、SSE/轮询。
- 先用 fake Worker 返回当前示例乐谱。
- 前端改为调用生成的 API client，不再直接依赖示例状态。

验收：上传 fixture 后可经历完整状态机、刷新恢复并显示示例谱；OpenAPI 契约测试通过。

### Phase 2：真实异步音频流水线（1–2 周）

- Redis + Celery Worker、FFmpeg、对象存储、取消/重试。
- 接入 Demucs 与 Basic Pitch；记录模型版本和中间产物。
- CPU/GPU 自动选择，OOM 转换为稳定错误码。

验收：完整歌曲上传后能返回 vocals stem、原始音符和可播放结果；API 在推理期间保持响应；Worker 重启后任务可恢复或明确失败。

### Phase 3：音乐分析与谱面质量（1–2 周）

- Beat This!、下拍、BPM/拍号、调性、动态规划主旋律和节奏量化。
- 建立带人工标注的回归评测集和基线报告。
- 支持用户确认/修正 BPM、拍号、调性后服务端重新量化。

验收：2/4、3/4、4/4、6/8 测试集可评测；质量指标达到 Beta 门槛或有明确差距报告。

### Phase 4：校对编辑器（2 周）

- 波形、钢琴卷帘、谱面双向定位；音符增删改、拆分合并。
- 撤销/重做、自动保存、revision 冲突处理。
- 原曲/stem/谱面混音、循环和调速。

验收：用户可以从有错误的自动结果完成校正，刷新页面不丢修改；E2E 覆盖完整编辑路径。

### Phase 5：导出、可观测性与 Beta（1 周）

- MIDI/MusicXML 后端导出，加入结构校验；可选 PDF。
- 结构化日志、任务耗时、队列长度、错误率、磁盘清理策略。
- 数据保留设置、删除项目、部署与备份文档。

验收：发布检查表全绿；从空环境按文档可部署；用户能删除所有项目数据；Beta 标签发布。

整体预计：单人全职约 6–8 周；若先做仅本地单用户版本，可暂缓 PostgreSQL/MinIO 的生产部署，但接口和适配器边界不变。

## 10. 首批 Issue 拆分

1. `chore(repo): initialize git and repository hygiene`
2. `chore(monorepo): move prototype into apps/web`
3. `feat(api): add health checks and OpenAPI contract`
4. `feat(api): implement upload and job state machine`
5. `feat(worker): add fake transcription adapter`
6. `feat(web): consume generated API client and job progress`
7. `feat(worker): add FFmpeg normalization`
8. `feat(worker): add Demucs separator adapter`
9. `feat(worker): add Basic Pitch transcription adapter`
10. `feat(worker): add Beat This beat/downbeat adapter`
11. `feat(score): implement canonical ScoreProject schema`
12. `feat(score): add monophonic path and quantization pipeline`
13. `feat(editor): add waveform and note timeline`
14. `feat(editor): add command history and autosave`
15. `feat(export): validate MIDI and MusicXML outputs`
16. `test(e2e): cover upload-to-export happy path`

## 11. 主要风险与缓解

- **模型许可与维护**：每个模型进入主分支前完成代码、权重、训练数据三层审查；通过适配器避免锁定。
- **GPU/Windows 兼容性**：CI 使用 CPU fake/小模型；提供 Docker GPU 与纯 CPU 降级路径；Windows 开发优先 WSL2/Docker Desktop。
- **长音频内存和超时**：限制上传大小，FFmpeg 流式处理，分段推理并在边界重叠合并。
- **自动谱面质量不足**：不覆盖原始音符；提供置信度、手动修正和回归评测，产品承诺是“高质量可编辑初稿”。
- **协议快速变化**：`schemaVersion`、数据库迁移和 OpenAPI 生成 client；破坏性变更必须写 ADR。
- **用户音频隐私**：默认私有、对象键不可猜、下载短期签名、明确保留期和彻底删除流程；日志不记录文件内容。

## 12. 开工顺序

不应一开始同时接入所有模型。严格按以下路径推进：

1. Git 基线与 monorepo；
2. fake Worker 打通 API 垂直切片；
3. FFmpeg + Demucs + Basic Pitch；
4. Beat This! 与谱面质量评测；
5. 编辑器；
6. 部署、可观测性和 Beta。

每个阶段都必须保留一个可运行、可演示的主分支，且以前一阶段的验收证据作为进入下一阶段的条件。

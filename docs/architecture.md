# 架构

## 组件

- `apps/web`：Vite + TypeScript 单页界面；负责上传、进度、谱面、播放、校音和下载。
- `apps/api`：FastAPI；负责上传、任务、项目 revision、重新量化和导出。
- `workers/transcription`：可由线程或 Celery 执行的推理管线。
- `packages/contracts`：前后端共享的 TypeScript 数据结构与 API 客户端。
- `infra`：PostgreSQL、Redis、MinIO、API、Worker 和 Web 容器定义。

## 数据流

```text
音频 → Upload → Job → FFmpeg → Demucs → Basic Pitch
                                  ↓
ScoreProject ← 后处理/量化 ← BPM 与调性估计
     ↓              ↓
revision 编辑      MIDI / MusicXML
```

`ScoreProject` JSON 是权威数据；MusicXML 和 MIDI 均为可重复生成的导出物。每次修改必须携带 `expected_revision`，过期客户端收到 HTTP 409，避免静默覆盖。

开发环境默认用 SQLite 和线程 Worker。容器环境用 PostgreSQL、Redis 和 Celery；API 与 Worker 共享 `/data`，生产化时可将本地存储适配器替换为 S3 兼容对象存储。

## 当前边界

- 目标是单一主唱的单旋律，不处理多乐器总谱。
- 真实管线的拍号暂定 4/4，BPM 来自音符起点间隔；后续应接入专用 beat/downbeat 模型。
- 当前编辑器覆盖音高校正和全局重新量化，尚未覆盖拖拽时值、拆分/合并与撤销栈。

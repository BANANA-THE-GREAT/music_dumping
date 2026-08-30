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

开发环境默认用 SQLite 和线程 Worker。线程 Worker 启动时会把上次进程中断的运行态任务标记为可重试失败，避免任务永久卡住。容器环境用 PostgreSQL、Redis 和 Celery；API 与 Worker 共享 `/data`，生产化时可将本地存储适配器替换为 S3 兼容对象存储。

## 当前边界

- 目标是单一主唱的单旋律，不处理多乐器总谱。
- 当前以音符起点和重音周期估计 BPM 与 2/4、3/4、4/4、6/8 拍号；专用 beat/downbeat 模型仍是后续质量升级项。
- 编辑器已支持钢琴卷帘拖拽音高、起点及时值，以及音符增删、缩放、拆分、合并、撤销/重做和 revision 自动保存。
- 原曲波形、简谱、五线谱与钢琴卷帘共享权威 `ScoreProject` 音符标识；刷新后可从最近项目恢复。

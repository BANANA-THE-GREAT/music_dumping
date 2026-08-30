# 拾音 · Vocal Score Studio

输入常见音频，生成可演奏、可校正的主旋律简谱与五线谱，并导出 MIDI / MusicXML。

## 已实现

- 三种转录模式：浏览器本地 Basic Pitch、后端快速演示、后端 Demucs + Basic Pitch 高质量管线
- 上传、持久化任务、SSE 进度、取消和稳定错误状态
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

```bash
docker compose -f infra/compose.yaml up --build
```

Web 默认位于 `http://localhost:8080`，API 位于 `http://localhost:8000`。API 容器启动前自动执行 Alembic migration。

## 验证

```bash
python -m ruff check apps/api workers
python -m mypy apps/api/app workers/transcription/vss_worker
python -m pytest
npm test
npm run build
```

更多说明见 [架构](docs/architecture.md)、[API](docs/api.md) 和 [模型许可](docs/model-licenses.md)。

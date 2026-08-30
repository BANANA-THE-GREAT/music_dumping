# HTTP API

基地址默认为 `http://localhost:8000`，交互式 OpenAPI 页面为 `/docs`。

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/v1/uploads` | 流式上传音频并计算 SHA-256 |
| POST | `/v1/jobs` | 创建转录任务；options 可选 fake 或 demucs/basic_pitch |
| GET | `/v1/jobs/{id}` | 获取任务状态 |
| GET | `/v1/jobs/{id}/events` | SSE 进度流 |
| POST | `/v1/jobs/{id}/cancel` | 取消非终态任务 |
| GET | `/v1/projects/{id}` | 获取 ScoreProject |
| PATCH | `/v1/projects/{id}` | 携带 expected_revision 更新音符 |
| POST | `/v1/projects/{id}/requantize` | 修改 BPM、拍号、调性和网格并重新量化 |
| GET | `/v1/projects/{id}/exports/midi` | 下载 MIDI |
| GET | `/v1/projects/{id}/exports/musicxml` | 下载 MusicXML |

revision 冲突返回 `409`，`detail.code` 为 `REVISION_CONFLICT`，并包含服务端 `current_revision`。

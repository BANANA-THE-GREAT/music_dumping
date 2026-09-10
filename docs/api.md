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
| GET | `/v1/projects/{id}/exports/staff.svg` | 下载谱面版五线谱 SVG；配置渲染服务时使用 Verovio，否则使用内置开发回退 |
| GET | `/v1/projects/{id}/exports/staff.png` | 通过 Verovio + Inkscape 下载五线谱 PNG |
| GET | `/v1/projects/{id}/exports/staff.pdf` | 通过 Verovio + Inkscape 下载五线谱 PDF |
| GET | `/v1/projects/{id}/exports/jianpu.svg` | 下载带稳定音符/休止段映射的简谱 SVG |
| GET | `/v1/projects/{id}/exports/jianpu.png` | 通过内置简谱 SVG + Inkscape 下载 PNG |
| GET | `/v1/projects/{id}/exports/jianpu.pdf` | 通过内置简谱 SVG + Inkscape 下载 PDF |

revision 冲突返回 `409`，`detail.code` 为 `REVISION_CONFLICT`，并包含服务端 `current_revision`。

图片导出不修改项目 revision。响应使用 `X-Score-Renderer` 和 `X-Score-Format` 标明实际链路。
需要 PNG/PDF 或生产五线谱 SVG 时，API 必须配置 `VSS_RENDERER_URL`；服务不可用返回 `503`
和 `SCORE_RENDERER_UNAVAILABLE`，刻谱或转换失败返回 `502` 和 `SCORE_RENDER_FAILED`。

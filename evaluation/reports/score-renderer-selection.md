# 谱面渲染器选型结论

日期：2026-09-10

## 结论

- 五线谱正式导出采用 Verovio `6.2.1`，输入为项目现有 MusicXML。
- 简谱正式导出采用项目内 SVG 布局器，直接读取谱面版 `ScoreNote`。
- Inkscape 只负责把受控 SVG 转换为 PNG/PDF，不参与音符语义和布局决策。
- OSMD Jianpu Display 不进入默认依赖；MuseScore Studio 与 LilyPond 只保留为人工出版质量对照。

## 对照结果

| 方案 | 离线固定 | 音符 ID 映射 | 简谱可用性 | 容器成本 | 决策 |
|---|---|---|---|---|---|
| 项目内 SVG | 是 | 直接保留 `data-note-id`、来源 ID 和休止区间 | 已实现短时值、附点、八度点、跨小节延音 | 低；仅转换阶段需要 Inkscape | 简谱主线 |
| Verovio 6.2.1 | 是 | MusicXML 可写稳定 segment ID，最终 SVG 映射待运行镜像实测 | 不提供本项目所需简谱 | 中 | 五线谱主线 |
| OSMD | 本体可固定 | 浏览器交互映射可行 | Jianpu Display 由上游标为 early access/sponsor 功能，当前不能作为公开、可复现依赖审查 | 中 | 不接入 Jianpu；无需下载不可审查构件 |
| MuseScore Studio | 可固定 | 静态导出后难以保持项目音符 ID | 简谱依赖额外模板、插件或字体，未形成可复现主线 | 高 | 只作人工视觉对照 |
| LilyPond | 可固定 | 需要新增 `.ly` 转换和额外映射 | 需要自定义简谱记谱层，重复项目内布局工作 | 高 | 只作远期五线谱回退 |

## 进入主线的依据

项目内简谱 SVG 不依赖远程字体或浏览器文本流，能够稳定输出音符、来源证据、休止段和
跨小节延音的定位属性。它与当前编辑器解耦，不会修改 `notes`、`performance_notes`、
量化、止音建议或音频对齐数据。

Verovio 通过独立 HTTP 容器运行，API 只发送 MusicXML。PNG/PDF 转换同样位于该容器，
不会向 API/Worker 镜像引入 GUI 工具，也不会在导出请求期间下载程序或字体。

## 未完成的运行证据

当前代码、单元测试和宿主机 Inkscape 转换已经通过；Verovio 容器因外部软件源下载超时尚未
完成首次构建。镜像构建后必须补充以下证据才能关闭最终验收：

- 读取 `/health` 中的 Verovio、Inkscape、字体和页面参数；
- 使用同一复杂节奏 fixture 生成五线谱/简谱 SVG、PNG、PDF；
- 检查文件类型、非空像素、裁切、中文标题、附点、连音和跨小节延音；
- 测试短谱、10 页和 50 页输入的耗时、内存与错误边界。

## 官方资料

- Verovio：<https://github.com/rism-digital/verovio>
- OSMD：<https://github.com/opensheetmusicdisplay/opensheetmusicdisplay>
- MuseScore CLI：<https://musescore.org/en/handbook/4/command-line-usage>
- LilyPond CLI：<https://lilypond.org/doc/v2.25/Documentation/usage/basic-command_002dline-options-for-lilypond>

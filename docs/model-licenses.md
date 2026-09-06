# 模型与依赖许可清单

本项目按非商业用途在 GitHub 公开开发。该用途约定不修改根目录 `LICENSE`，也不替换第三方许可。
部署或分发模型前必须固定版本，分别核对代码 LICENSE、权重授权、模型卡和训练数据已知条款。
本仓库不提交模型权重、用户音频或未经授权的标注数据。

## 项目登记

以下为 2026-09-06 的调研与接入状态。未填精确版本和权重哈希的候选，不视为已完成集成审查。

| 组件 | 状态及用途 | 官方来源 | 已知许可和待办 |
|---|---|---|---|
| Demucs | 已接入，人声分离 | [代码](https://github.com/facebookresearch/demucs) | 补齐当前固定版本、实际权重来源与哈希，并分别归档授权 |
| Spotify Basic Pitch | 已接入，复音转录与回退基线 | [Python](https://github.com/spotify/basic-pitch)、[TypeScript](https://github.com/spotify/basic-pitch-ts) | Python 代码 Apache-2.0；TS 和所用权重分别核对并归档 |
| abcjs | 已接入，五线谱刻谱 | [代码](https://github.com/paulrosen/abcjs) | 按实际安装版本补齐许可证及必要声明 |
| GAME | 优先候选，歌声专用转录 | [代码](https://github.com/openvpi/GAME)、[权重](https://github.com/openvpi/GAME/releases/tag/v1.0.0) | 代码 MIT；官方 1.0 权重 CC BY-NC-SA 4.0；不是已接入功能 |
| SOME | 评测候选，轻量转录对照 | [代码](https://github.com/openvpi/SOME)、[权重](https://github.com/openvpi/SOME/releases/tag/v1.0.0-baseline) | 代码 MIT；所列官方基线权重 CC BY-NC-SA 4.0 |
| ROSVOT | 按需备选，歌声转 MIDI | [代码与模型说明](https://github.com/RickyL-2000/ROSVOT) | 代码 MIT；权重及训练数据使用限制待核实，不自动继承 MIT |
| RMVPE | 候选，连续基频校验 | [原实现](https://github.com/Dream-High/RMVPE)、[部署实现](https://github.com/yxlllc/RMVPE) | 尚未决定具体实现及 checkpoint；代码与权重授权待分别核实 |
| DDSP | 可选后续研究，重合成校验 | [代码](https://github.com/magenta/ddsp) | 尚未集成；若使用具体预训练音色模型，须额外核查权重和数据授权 |

## 集成与公开发布检查表

- [ ] 记录项目名称、用途、代码版本或 commit、模型配置和运行依赖。
- [ ] 记录权重官方来源、文件名、SHA-256、对应许可证原文或稳定链接。
- [ ] 分别确认代码、权重、数据集的使用及再分发条件；不以代码许可推断权重许可。
- [ ] 对非商用模型保留非商用说明、署名和许可证链接；若修改或分发衍生材料，核实并履行适用的相同方式共享义务。
- [ ] 不将权重、歌曲或 stem 打包进 GitHub 仓库、Release 或公共容器镜像，除非另行完成明确的分发许可审查；默认仅提供官方下载方式。
- [ ] 发布评测结果前核实音频、歌词和人工标注的公开授权，私有数据只保存本地引用。
- [ ] 同步根目录 README 的依赖状态，不把候选写成已接入。
- [ ] 用途或分发方式变化时重新审核，不能沿用“本项目非商用”作为任意使用的授权。

实施顺序与验收见 [人声转 MIDI 质量升级计划](../plan/vocal-to-midi-quality.md)。

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
| GAME | 优先候选，歌声专用转录；未接入 | [代码](https://github.com/openvpi/GAME)、[权重](https://github.com/openvpi/GAME/releases/tag/v1.0.0) | 固定代码 tag `v1.0.0` / commit `e66c31251605e334b1bf0f565252d4987a9065c0`，代码 MIT。官方 small/medium/large 1.0 权重为 CC BY-NC-SA 4.0，训练含约 32 小时私有人工标注数据及公开/私有噪声数据；接入前下载实际采用的 zip 并记录 SHA-256 |
| SOME | 评测候选，轻量转录对照；未接入 | [代码](https://github.com/openvpi/SOME)、[权重](https://github.com/openvpi/SOME/releases/tag/v1.0.0-baseline) | 固定代码 tag `v1.0.0-baseline` / commit `dcfd40f9bfaa7c9649aae01a2795af73946ec5e7`，代码 MIT。官方 `0119_continuous128_5spk.zip` 权重为 CC BY-NC-SA 4.0；接入前记录下载文件 SHA-256 |
| ROSVOT | 按需备选，歌声转 MIDI | [代码与模型说明](https://github.com/RickyL-2000/ROSVOT) | 代码 MIT；权重及训练数据使用限制待核实，不自动继承 MIT |
| RMVPE | 候选，连续基频校验；未接入 | [原实现](https://github.com/Dream-High/RMVPE)、[部署实现](https://github.com/yxlllc/RMVPE) | 原实现预检 commit `a6db1cd7d26014aa739383367afd9bab57fc624c`；部署实现最新可见权重 release `230917`，说明训练数据包含处理后的 MIR-1K、PTDB 和 M4Singer 合成数据。代码许可、权重许可及各训练数据约束仍未完整核实，不得下载后直接分发或接入默认链路 |
| DDSP | 可选后续研究，重合成校验 | [代码](https://github.com/magenta/ddsp) | 尚未集成；若使用具体预训练音色模型，须额外核查权重和数据授权 |

## 评测数据集

| 数据集 | 状态及用途 | 官方来源 | 许可和存储约束 |
|---|---|---|---|
| Vocadito | 已用于 P0 孤立人声基线；40 段双音符标注及 F0 | [Zenodo](https://zenodo.org/records/5578807)，DOI `10.5281/zenodo.5578807` | 作者：Rachel Bittner、Katherine Pasalo、Juan José Bosch、Gabriel Meseguer Brocal、David Rubinstein；CC BY 4.0。归档 SHA-256 `e0d6b99d3f9c594afe5ae5c4d7bdacebe569e53b809e90b89d1c771c4f9990e3`；音频和转换标注仅保存在本机 `data/`，仓库记录归属、划分和汇总指标 |

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

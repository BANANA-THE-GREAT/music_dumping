# 模型与依赖许可清单

本项目按非商业用途在 GitHub 公开开发。该用途约定不修改根目录 `LICENSE`，也不替换第三方许可。
部署或分发模型前必须固定版本，分别核对代码 LICENSE、权重授权、模型卡和训练数据已知条款。
本仓库不提交模型权重、用户音频或未经授权的标注数据。

## 项目登记

以下为 2026-09-10 的调研与接入状态。未填精确版本和权重哈希的候选，不视为已完成集成审查。

| 组件 | 状态及用途 | 官方来源 | 已知许可和待办 |
|---|---|---|---|
| Demucs | 已接入，人声分离 | [代码](https://github.com/facebookresearch/demucs) | 补齐当前固定版本、实际权重来源与哈希，并分别归档授权 |
| Spotify Basic Pitch | 已接入，复音转录与回退基线 | [Python](https://github.com/spotify/basic-pitch)、[TypeScript](https://github.com/spotify/basic-pitch-ts) | Python 代码 Apache-2.0；TS 和所用权重分别核对并归档 |
| abcjs | 已接入，五线谱刻谱 | [代码](https://github.com/paulrosen/abcjs) | 按实际安装版本补齐许可证及必要声明 |
| Verovio | 已接入独立谱面渲染容器，将 MusicXML 刻制为五线谱 SVG | [代码与发布](https://github.com/rism-digital/verovio) | 固定 Python 包 `6.2.1`；上游声明 LGPL，并包含需随分发保留的 LGPL/GPL 文件。当前通过独立 HTTP 服务调用，不复制源码或二进制进应用包 |
| Inkscape | 已接入独立谱面渲染容器，将 SVG 转换为 PNG/PDF | [许可说明](https://inkscape.org/about/license/) | Debian 软件包版本随 `python:3.11.16-slim-trixie` 仓库解析，镜像构建后记录实际版本；程序为 GPL。项目仅通过命令行子进程调用；官方说明其导出文件不因运行 Inkscape 自动受 GPL 约束 |
| Noto CJK | 已接入渲染容器，提供中文标题和符号的本地字体回退 | [字体仓库](https://github.com/notofonts/noto-cjk) | `fonts-noto-cjk` Debian 包，构建后记录实际包版本；字体为 SIL OFL 1.1。重新分发镜像时保留版权和许可文本，不单独出售字体 |
| OpenSheetMusicDisplay | 尚未接入；仅作为浏览器刻谱候选 | [代码](https://github.com/opensheetmusicdisplay/opensheetmusicdisplay) | 本体 BSD-3-Clause；上游仍把 Jianpu Display 列为 early access/sponsor 功能，不能把本体许可证直接推断为该功能的可用授权 |
| MuseScore Studio / LilyPond | 尚未接入；出版级五线谱回退候选 | [MuseScore](https://github.com/musescore/MuseScore)、[LilyPond](https://gitlab.com/lilypond/lilypond) | 真正接入前固定版本并核对 GPL、字体、插件和容器再分发要求；当前不得写成已提供功能 |
| GAME | 已接入显式可选的本地 quality Worker；默认仍为 Basic Pitch | [代码](https://github.com/openvpi/GAME)、[权重](https://github.com/openvpi/GAME/releases/tag/v1.0.0) | 固定代码 tag `v1.0.0` / commit `e66c31251605e334b1bf0f565252d4987a9065c0`，源码归档 SHA-256 `41188c7b0f9f4baf0a7b9ad0621c20f643d8c90751b92221493f49e8aeef47d4`，代码 MIT；官方权重 CC BY-NC-SA 4.0。small zip SHA-256 `3d3e1ac0a83234b2a163a3d43043455d15670765eaa25ef6285c399da1ccc576`，`model.pt` SHA-256 `7dd10022a4011938843249a31d9527691376c493d13687a7fc1dec88786b9691`；medium zip SHA-256 `8c5b3e531e2905b935e664e2f533921cd637243770fab5282413bdb5051ca60c`，`model.pt` SHA-256 `e9904159fb0646e1a352b9d2bc74615547cfa3e32d45c7464d440ac142846d93`。medium 权重通过宿主机 `data/` 只读挂载，不打包进镜像。训练含约 32 小时私有人工标注数据及公开/私有噪声数据 |
| SOME | P1 独立 CPU 对照完成；未接入默认 Worker | [代码](https://github.com/openvpi/SOME)、[权重](https://github.com/openvpi/SOME/releases/tag/v1.0.0-baseline) | 固定代码 tag `v1.0.0-baseline` / commit `dcfd40f9bfaa7c9649aae01a2795af73946ec5e7`，代码 MIT；权重 CC BY-NC-SA 4.0。`0119_continuous128_5spk.zip` SHA-256 `bc91b1afc3ae350bd70d36ec418c471baa65c94fbeeaa09d6e178cbcfca886ec`；压缩包内部实际为 `0119_continuous256_5spk`，checkpoint SHA-256 `aa710fce920b4dae281b0e6cc2acba83345d82ee62d51f7bafeb29636f28f97c` |
| ROSVOT | 按需备选，歌声转 MIDI | [代码与模型说明](https://github.com/RickyL-2000/ROSVOT) | 代码 MIT；权重及训练数据使用限制待核实，不自动继承 MIT |
| RMVPE | 暂停，连续基频候选；未接入 | [原实现](https://github.com/Dream-High/RMVPE)、[部署实现](https://github.com/yxlllc/RMVPE) | 原实现 commit `a6db1cd7d26014aa739383367afd9bab57fc624c` 含 Apache-2.0 LICENSE，但未发布权重。部署实现 commit `0aabafba18289ca938a73af0b0297686abf4922d` 及 `230917` release 提供约 325 MiB 权重，却未提供明确代码 LICENSE 或权重授权；不得接入、再分发或把其结果宣传为已审核模型 |
| torchcrepe / CREPE | 已接入可选本地 quality Worker，用于 10ms F0 证据和人工审阅建议；不进入默认自动修正 | [torchcrepe](https://github.com/maxrmorrison/torchcrepe)、[CREPE](https://github.com/marl/crepe) | 固定 torchcrepe `0.0.24` / commit `19e2ec3d494c0797a5ff2a11408ec5838fba6681`，仓库 MIT，并说明包内权重由原始 CREPE tiny/full 权重转换。源码归档 SHA-256 `4c4651da5c071f81d7825ed58edc32b42f74e794152ff45d9b08432e882e8f91`；full 权重 SHA-256 `133225604dedd2e4005f8bbd1bd0a2ec073ba8b7a6cd31ff6d5edbbfa3539986`。权重只进入本地 quality 镜像，不提交 Git 或公共 Release；公开容器前仍需保留 MIT notice 并复核原始 CREPE 训练数据说明 |
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

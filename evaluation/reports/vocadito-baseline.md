# Vocadito Basic Pitch 基线报告

日期：2026-09-07

## 数据与划分

- 数据集：Vocadito，Rachel Bittner、Katherine Pasalo、Juan José Bosch、Gabriel Meseguer Brocal、David Rubinstein，DOI `10.5281/zenodo.5578807`，CC BY 4.0。音频和转换后的标注保存在本机 `data/`，不提交 Git。
- ZIP：MD5 `dea40fd18f14d899643c4ba221b33a46`；SHA-256 `e0d6b99d3f9c594afe5ae5c4d7bdacebe569e53b809e90b89d1c771c4f9990e3`。
- 40 段全部纳入：25 段 tuning、15 段 holdout，按 `singer_id` 隔离，无歌手泄漏。
- A1 为主参考，A2 用于不确定区域。A1/A2 的宏平均起音 F1 为 tuning 0.7366、holdout 0.7447；起止 F1 为 tuning 0.6327、holdout 0.6579。

## 固定基线

- Docker Worker，Python 3.11，CPU 推理。
- Basic Pitch 0.4.0；模型目录 SHA-256 `095cf7e8a2205331d9cd05d545f49c4a51d5826e7f385d1bfb8657b9ff3d0e33`。
- 首次模型加载和首段推理约 12.31 秒，全部 40 段累计约 19.87 秒；稳态单段中位数约 0.18 秒，峰值 RSS 约 877 MiB。
- 整理参数和 120 BPM 四分之一拍量化参数见 `evaluation/baseline-config.json`。

## 结果

| 集合 | 阶段 | 起音 F1 | 起止 precision | 起止 recall | 起止 F1 |
|---|---|---:|---:|---:|---:|
| tuning | Basic Pitch raw | 0.4710 | 0.3295 | 0.2893 | 0.3034 |
| tuning | 整理后 | 0.4649 | 0.3812 | 0.2674 | 0.3078 |
| tuning | 固定 BPM 量化后 | 0.3893 | 0.2901 | 0.2050 | 0.2354 |
| holdout | Basic Pitch raw | 0.5120 | 0.3255 | 0.3140 | 0.3128 |
| holdout | 整理后 | 0.4775 | 0.3912 | 0.2830 | 0.3156 |
| holdout | 固定 BPM 量化后 | 0.3733 | 0.2588 | 0.2007 | 0.2190 |

完整逐片段指标见 `vocadito-basic-pitch.json`。

## 损失定位

- 2086 个原始候选经整理后剩 1569 个，共减少 517 个事件。
- 默认 MIDI 48 至 84 音域过滤了 272 个候选，是最大的显式过滤来源。
- 201 次短同音片段被合并；另有 5 个已选片段因短于 60 ms 被删除，1 个候选因置信度低于 0.2 被删除。
- holdout 中整理提高了起止 precision，但降低 recall 3.1 个百分点，并使起音 F1 下降 0.0345，说明连续性/音域规则压掉了部分真实事件。
- 固定 120 BPM 四分之一拍量化使 holdout 起止 F1 从 0.3156 降至 0.2190，证明过早固定速度和粗网格造成显著时间损失。

## 边界与后续

本报告只证明孤立人声上的基线和损失位置。Vocadito 不覆盖 Demucs 分离残留、伴奏串音、真实流行混音或人工修谱耗时；这些场景仍需项目自有或另行授权样本补充。达到预登记门槛前不更换默认引擎。

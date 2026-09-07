# Vocadito GAME tuning 诊断

日期：2026-09-07

## 范围与选择规则

- 只使用 singer-disjoint tuning 集的 25 段，未运行调参后的 holdout 推理。
- 模型固定为 GAME 1.0 medium，CPU、随机种子 `114514`、language ID `0`。
- 粗网格覆盖 presence threshold `0.10/0.15/0.20` 与 boundary threshold `0.10/0.20`，D3PM 固定 8 步。
- 阈值网格失败后，在访问 tuned holdout 前增加一次 16-step 诊断。
- 候选必须完整、失败率合格、precision 回退不超过 `0.02` 且起止 F1 至少提高 `0.03`；之后按起止 recall、F1 排序。无候选满足 F1 条件时只报告诊断性 fallback，不进入 holdout。

## Tuning 结果

| 配置（presence / boundary / steps） | 起止 precision | 起止 recall | 起止 F1 | recall 增量 | F1 增量 | tuning 门槛 |
|---|---:|---:|---:|---:|---:|---|
| Basic Pitch raw | 0.3295 | 0.2893 | 0.3034 | - | - | 基线 |
| 0.10 / 0.10 / 8 | 0.3164 | 0.2948 | 0.3039 | +0.0055 | +0.0005 | 未通过 |
| 0.10 / 0.20 / 8 | 0.3261 | 0.2785 | 0.2992 | -0.0108 | -0.0042 | 未通过 |
| 0.15 / 0.10 / 8 | 0.3168 | 0.2948 | 0.3041 | +0.0055 | +0.0007 | 未通过 |
| 0.15 / 0.20 / 8 | 0.3269 | 0.2785 | 0.2995 | -0.0108 | -0.0039 | 未通过 |
| 0.20 / 0.10 / 8 | 0.3168 | 0.2948 | 0.3041 | +0.0055 | +0.0007 | 未通过 |
| 0.20 / 0.20 / 8 | 0.3272 | 0.2785 | 0.2997 | -0.0108 | -0.0037 | 未通过 |
| 0.15 / 0.10 / 16 | 0.3168 | 0.2948 | 0.3041 | +0.0055 | +0.0007 | 未通过 |

机器选择器给出的 fallback 是 `0.15 / 0.10 / 8`，但它没有通过 tuning 门槛。presence 在本次范围内几乎不改变 recall；降低 boundary threshold 只能带来约 `0.0163` 的模型内 recall 改善。16 步与 8 步指标完全相同，因此没有证据表明 D3PM 采样不足是当前瓶颈。

## 根因判断

最佳 tuning 配置的音高+起音 precision/recall/F1 为 `0.6549/0.6129/0.6305`，Basic Pitch raw 为 `0.5065/0.4519/0.4710`。GAME 明显改善了音符起音检测，但加入止音约束后 F1 仅从 `0.3034` 到 `0.3041`。

严格起止匹配下，GAME 相对 Basic Pitch 的 missed notes 从 `1030` 降到 `1007`，extra notes 从 `893` 增到 `910`；possible splits 从 `180` 降到 `137`，possible merges 从 `105` 降到 `92`。结果更符合“音符事件方向有效、结束边界仍不稳定”，而不是“阈值过高导致大量真实音符完全未输出”。

逐片段差异很大：部分 Catalan、Spanish、French 及 English 片段明显改善，也有 French/English 片段显著回退。该波动不足以支持按语言做统一假设，后续需结合连续 F0、发声区间和 A1/A2 标注分歧定位边界误差。

## 决策

- 停止继续扩大 GAME 阈值或 D3PM 网格，不用 holdout 追逐参数。
- 不训练或微调 GAME；当前证据尚未证明训练数据量是主因。
- 默认引擎继续使用 Basic Pitch，GAME medium 只保留为实验候选。
- 将连续 F0/RMVPE 诊断提前到默认候选接入之前，验证是否能局部校正 GAME 的止音边界和漏音提示。
- 只有在 tuning 上形成固定的 GAME+F0 规则后，才允许对未访问的 holdout 做一次最终评测。

完整机器可读结果见 `vocadito-game-tuning.json`；可复现实验入口为 `scripts/run-game-tuning-sweep.sh`。

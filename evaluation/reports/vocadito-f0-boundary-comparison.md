# Vocadito 连续 F0 边界诊断

日期：2026-09-07

## 实现选择

RMVPE 原始仓库代码为 Apache-2.0，但常用部署仓库及 `230917` 权重没有明确 LICENSE 或权重授权，因此未接入。P3 诊断改用 [torchcrepe](https://github.com/maxrmorrison/torchcrepe) `0.0.24` / commit `19e2ec3d494c0797a5ff2a11408ec5838fba6681`；仓库为 MIT，并说明包内 tiny/full 权重由原始 CREPE 权重转换而来。

实验固定使用 full 权重 SHA-256 `133225604dedd2e4005f8bbd1bd0a2ec073ba8b7a6cd31ff6d5edbbfa3539986`，CPU、10ms hop、Viterbi 解码、50–1100 Hz、3 帧 periodicity 中值滤波和 -60dB 静音抑制。权重只存在于本地实验镜像，不进入 Git。

## F0 tuning 验证

在 25 段 tuning 与 Vocadito F0 标注对齐后，periodicity `0.50` 的 voicing precision/recall/F1 为 `0.9065/0.9352/0.9206`；50 cents pitch precision/recall/F1 为 `0.8959/0.9243/0.9099`，已发声帧 raw pitch accuracy 为 `0.9883`。

只移动 GAME 止音、不改变起音和音高的边界网格选择了 periodicity `0.40`、音高容差 `100 cents`、最大 F0 间断 `20ms`。最大收缩和延长均限制为 `400ms`，且不能跨越下一音符起音。

| Tuning 参考 | 配置 | 起止 precision | recall | F1 |
|---|---|---:|---:|---:|
| A1 | GAME tuned | 0.3168 | 0.2948 | 0.3041 |
| A1 | GAME + F0 边界 | 0.4617 | 0.4284 | 0.4426 |
| A2 | GAME tuned | 0.3666 | 0.4091 | 0.3859 |
| A2 | GAME + F0 边界 | 0.5099 | 0.5683 | 0.5364 |

## 固定 holdout

只有在 tuning 规则写入 `evaluation/f0-holdout-config.json` 后，才运行一次 15 段 holdout。未根据 holdout 修改参数。

| Holdout / A1 | 起音 F1 | 起止 precision | recall | F1 |
|---|---:|---:|---:|---:|
| Basic Pitch raw | 0.5120 | 0.3255 | 0.3140 | 0.3128 |
| GAME tuned | 0.6778 | 0.3818 | 0.3486 | 0.3631 |
| GAME + F0 边界 | 0.6778 | 0.4683 | 0.4194 | 0.4407 |

GAME + F0 相对 Basic Pitch raw 的 precision/recall/F1 分别提高 `0.1428/0.1054/0.1279`，通过预登记的 F1 `+0.03`、recall `+0.05`、precision 回退和失败率门槛。A2 严格起止 F1 也从 GAME 的 `0.4733` 提高到 `0.5881`。

边界修正保持起音和音高不变，将 A1 起音匹配音符的平均止音误差从 `86.39ms` 降到 `70.95ms`。GAME 和 F0 均完成 15/15 段且无推理失败。GAME holdout CPU 推理约 `453.0s`；torchcrepe 约 `417.8s`，中位数 `24.07s/段`，峰值 RSS 约 `2105 MiB`。

## 限制与决策

- A1 逐片段为 9 段改善、1 段不变、5 段回退；最差单段 F1 回退约 `0.0964`。A2 为 13 段改善、2 段回退。
- Vocadito 是干净孤立人声，尚未覆盖 Demucs 残留、伴奏串音、合唱或真实长歌曲。
- 当前规则修改 15 段中的 515 个候选止音，不能在生产环境无提示地覆盖用户结果。
- GAME 和 torchcrepe 串行 CPU 成本较高，GAME 取消问题也尚未解决。

结论：连续 F0 校正方向通过质量验证，原计划可以继续。但下一步应接入为显式实验引擎和可审阅的边界建议，默认关闭自动应用；完成取消、持久化、回退、真实混音评测及逐片段回归保护前，默认引擎仍保持 Basic Pitch。

机器报告为 `vocadito-f0-diagnostics.json` 和 `vocadito-f0-holdout.json`，复现入口为 `scripts/run-f0-boundary-benchmark.sh`。

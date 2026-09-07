# Vocadito 歌声专用模型对比

日期：2026-09-07

## 实验设置

- 同一 Vocadito singer-disjoint 划分：25 段 tuning、15 段 holdout。
- 所有模型比较未量化音符，统一使用 50 cents 音高、50 ms 起音及 `max(50 ms, 参考时值 20%)` 止音容差。
- GAME 固定 D3PM 8 步、阈值 0.2、batch size 4、语言 ID 0；GAME 与 SOME 均固定随机种子 `114514`。
- 当前 Docker 无 NVIDIA runtime，全部为 CPU 结果。逐段输出和 runtime 留在 Git 忽略的 `data/`。

## Holdout 质量

| 模型 | 起音 F1 | 起止 precision | 起止 recall | 起止 F1 | 相对基线起止 F1 |
|---|---:|---:|---:|---:|---:|
| Basic Pitch raw | 0.5120 | 0.3255 | 0.3140 | 0.3128 | - |
| GAME 1.0 small | 0.6671 | 0.3897 | 0.3326 | 0.3576 | +0.0448 |
| GAME 1.0 medium | 0.6662 | 0.3864 | 0.3426 | 0.3620 | +0.0492 |
| SOME continuous256 5spk | 0.6409 | 0.3586 | 0.3276 | 0.3415 | +0.0287 |

GAME 显著改善起音识别，medium 的起止 F1 最高。small 与 medium 的起止 F1 增幅通过 `+0.03` 门槛，precision 无回归且 40 段均成功；但 recall 增幅只有 `+0.0186` 和 `+0.0286`，未达到预登记的 `+0.05`。SOME 的 F1 和 recall 增幅均未达标。因此没有候选通过全部质量门槛。

## CPU 资源

| 模型 | 加载 | 40 段推理 | 平均每段 | 峰值 RSS | 失败 |
|---|---:|---:|---:|---:|---:|
| Basic Pitch 0.4.0 | 首段含加载 12.31s | 19.87s | 稳态中位数 0.18s | 约 877 MiB | 0 |
| GAME 1.0 small | 0.31s | 250.22s | 6.26s | 约 1180 MiB | 0 |
| GAME 1.0 medium | 1.67s | 531.57s | 13.29s | 约 1579 MiB | 0 |
| SOME continuous256 5spk | 1.33s | 153.32s | 3.83s，中位数 3.43s | 约 1356 MiB | 0 |

加载时间受 Linux page cache 影响，仅用于本机预算。两个实验镜像都从本地 Worker 基础镜像派生，镜像约 4.65 GB，不作为最终生产镜像体积目标。

## 取消与结论

- GAME medium 在推理中执行 `docker stop -t 10`，10.39 秒后被强制终止，退出码 137。
- SOME 在推理中执行相同命令，9.24 秒后该片段自然完成并退出 0，未表现出及时响应 SIGTERM。
- 两者目前只能依赖容器超时硬终止，不满足直接接入后台任务所需的快速协作取消。

默认引擎继续使用 Basic Pitch。GAME medium 保留为最佳实验候选，但不能进入 P2 默认接入；后续若接入实验模式，必须先解决取消、真实混音/Demucs 残留覆盖和新的未访问 holdout。完整逐片段结果见 `vocadito-candidates.json`，机器可读门槛判定见 `vocadito-candidate-summary.json`。

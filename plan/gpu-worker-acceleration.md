# Worker GPU 加速计划

状态：已完成。2026-09-08 已在 NVIDIA GeForce RTX 5060 Ti 上完成 CUDA 容器、模型 holdout、真实 API 任务和取消验收。默认 Worker 与 CPU 回退保持不变，GPU quality Worker 使用 PyTorch `2.8.0+cu128` 镜像 `4c651676e3e7`。

## 现状证据

- 默认 Worker 继续从 PyTorch CPU index 安装依赖；只有叠加 `infra/compose.gpu.yaml` 或运行 GPU quality 构建脚本时安装 CUDA wheel 和申请 GPU。
- 容器内实测 PyTorch `2.8.0+cu128`、CUDA `12.8`，`torch.cuda.is_available() == True`，设备为 NVIDIA GeForce RTX 5060 Ti 16 GiB。
- 2026-09-07 的 `vocadito_20.wav` 实际任务总耗时 `41.99s`。流水线记录 Demucs `5.78s`，GAME + torchcrepe 合计 `35.63s`，音乐分析 `0.32ms`。当前记录无法再拆分 GAME 与 torchcrepe 的耗时。
- 接口实施后的同一片段 CPU 冒烟已能拆分耗时：GAME `19.45s`、torchcrepe `14.74s`，产出 32 个音符和 872 帧 F0；两项 provenance 均记录实际设备为 `cpu`。
- GPU 首轮端到端任务峰值显存 `3399 MiB`、峰值利用率 `73%`。诊断发现 Demucs GPU 计算约 `1.00s`，但 Hugging Face 远端元数据检查令缓存模型加载耗时 `69.41s`；设置 `HF_HUB_OFFLINE=1` 后模型加载降至 `0.34s`，因此 GPU override 默认离线读取持久化模型缓存。
- 15 段 holdout 上 GAME 核心推理由 CPU `453.02s` 降至 GPU `17.42s`，约 `26.0x`；torchcrepe 总耗时由 `417.76s` 降至 `40.76s`，约 `10.2x`，其中首段包含 CUDA 初始化。
- 同一 Vocadito 真实 API 任务由 CPU 参考约 `41.99s` 降至 GPU `25.53s`，约 `1.64x`；其中 Demucs `2.98s`、GAME `14.19s`、torchcrepe `6.39s`，端到端峰值显存 `3352 MiB`、峰值 GPU 利用率 `83%`。
- 空闲时项目 Worker 约占 `0.10% CPU`，高 CPU 主要发生在模型推理或 Docker 镜像构建期间，不是已观察到的常驻忙循环。

## 迁移范围与顺序

1. [x] 为 GAME 与 torchcrepe 分别记录耗时和所选设备，先定位 `35.63s` 中的主要成本；峰值显存仍待 GPU 实测。
2. [x] 为 GAME 和 torchcrepe 增加 `VSS_INFERENCE_DEVICE=auto|cpu|cuda`；`auto` 只有在 `torch.cuda.is_available()` 为真时选择 CUDA，否则回退 CPU。
3. [x] 为 Demucs 显式传入 `--device`，使用同一设备策略，并在项目 provenance 中记录实际设备。
4. [x] 保留 CPU 默认构建；新增 CUDA 构建参数和独立 Compose override，不让没有 NVIDIA 环境的默认启动命令失效。
5. [x] 分别基准 Demucs、GAME、torchcrepe；三者在 16 GiB 显存下串行共用 GPU，Celery 仍保持单并发。

Basic Pitch、FFmpeg 归一化、节拍/调性/拍号分析、旋律后处理和 API/Web 不列入首轮 GPU 迁移。它们要么不使用当前 PyTorch 路径，要么在实测流水线中的成本很低。

## 主机前置条件

- [x] 已运行 `scripts/setup-nvidia-container-toolkit.sh`，安装 NVIDIA Container Toolkit `1.19.0-1` 并完成 Docker runtime 配置；容器内已识别 NVIDIA GeForce RTX 5060 Ti。
- 在修改项目镜像前，必须先让一个已有本地镜像通过 `--gpus all` 启动，并在容器内确认 `torch.cuda.is_available()`。
- CUDA PyTorch 版本必须通过 RTX 5060 Ti 的实际容器测试确定，不能只根据宿主机能运行 `nvidia-smi` 判断兼容。

## 验收标准

- 默认 `infra/compose.yaml` 仍能在纯 CPU 主机启动并完成 Basic Pitch 与实验引擎的既有测试。
- GPU override 启动后，Worker 健康检查或诊断命令同时报告 GPU 型号、PyTorch/CUDA 版本和 `torch.cuda.is_available() == True`。
- Demucs、GAME、torchcrepe 的 provenance 分别记录实际设备与耗时，不再使用笼统的 `worker-default`。
- 使用同一输入分别运行 CPU/GPU，音符、F0 帧数和人声 stem 满足既定等价容差；取消任务仍能终止模型子进程。
- 分阶段报告墙钟耗时、CPU 使用、峰值显存和加速比。若某阶段 GPU 没有稳定收益或发生显存不足，该阶段保持 CPU。

## 实机验收结果

- `scripts/run-gpu-holdout-benchmark.sh` 在 15 段 singer-disjoint holdout 上完成且无推理失败。GAME 的起音+音高 F1 相对 CPU 变化 `-0.0122`，严格起止+音高 F1 变化 `+0.0018`，均通过最大 `0.03` 回退门槛。
- torchcrepe CPU/GPU 的 32,401 帧数量一致，voicing 判定零分歧。两者直接音高 MAE 为 `9.27 cents`，未达到原数值一致性目标 `5 cents`；该差异中位数 `7.98 cents`、95 分位 `22.11 cents`、最大 `37.67 cents`，全部低于项目的 `50 cents` 音高容差。
- CPU 输出不是音高真值，因此直接 MAE 保留为数值诊断，不作为质量替代指标。分别对 Vocadito 公开 F0 真值评估后，GPU 的 50-cents pitch F1 仅变化 `-0.00010`，raw pitch accuracy 变化 `-0.00012`，通过最大 `0.005` 回退门槛。机器报告为 `evaluation/reports/gpu-holdout-comparison.json`。
- 真实 GPU 任务取消后 API 状态转换约 `41ms`，Worker 随后约 `70ms` 清理完成；无 GAME/torchcrepe 子进程残留，显存回到空闲基线。

## 回退方案

GPU 镜像、Compose override 和设备配置均保持可选。删除 override 或设置 `VSS_INFERENCE_DEVICE=cpu` 即回到现有 CPU 路径，不迁移数据库数据，也不改变默认转录引擎。

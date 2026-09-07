# Worker GPU 加速计划

状态：接口已实施，实机 GPU 验收待完成。2026-09-07 已加入 CUDA PyTorch 构建参数、GPU Compose override、统一设备选择和 provenance；宿主机仍未安装或注册 NVIDIA Container Toolkit，当前容器无法完成 CUDA 实测。

## 现状证据

- `docker run --rm --gpus all vocal-score-studio-worker:latest ...` 返回 `could not select device driver ... [[gpu]]`。
- 默认 Worker 从 PyTorch CPU index 安装依赖；quality Worker 重新安装 CPU 版 `torch==2.8.0`，并设置 `CUDA_VISIBLE_DEVICES=""`。
- torchcrepe CLI 固定使用 `device="cpu"`；GAME 和 torchcrepe 子进程会把 PyTorch 线程数设为全部宿主机 CPU 核心。
- 2026-09-07 的 `vocadito_20.wav` 实际任务总耗时 `41.99s`。流水线记录 Demucs `5.78s`，GAME + torchcrepe 合计 `35.63s`，音乐分析 `0.32ms`。当前记录无法再拆分 GAME 与 torchcrepe 的耗时。
- 接口实施后的同一片段 CPU 冒烟已能拆分耗时：GAME `19.45s`、torchcrepe `14.74s`，产出 32 个音符和 872 帧 F0；两项 provenance 均记录实际设备为 `cpu`。
- 空闲时项目 Worker 约占 `0.10% CPU`，高 CPU 主要发生在模型推理或 Docker 镜像构建期间，不是已观察到的常驻忙循环。

## 迁移范围与顺序

1. [x] 为 GAME 与 torchcrepe 分别记录耗时和所选设备，先定位 `35.63s` 中的主要成本；峰值显存仍待 GPU 实测。
2. [x] 为 GAME 和 torchcrepe 增加 `VSS_INFERENCE_DEVICE=auto|cpu|cuda`；`auto` 只有在 `torch.cuda.is_available()` 为真时选择 CUDA，否则回退 CPU。
3. [x] 为 Demucs 显式传入 `--device`，使用同一设备策略，并在项目 provenance 中记录实际设备。
4. [x] 保留 CPU 默认构建；新增 CUDA 构建参数和独立 Compose override，不让没有 NVIDIA 环境的默认启动命令失效。
5. 分别基准 Demucs、GAME、torchcrepe 后再决定是否允许它们共用 GPU。16 GiB 显存下先串行执行，不默认增加 Celery 并发。

Basic Pitch、FFmpeg 归一化、节拍/调性/拍号分析、旋律后处理和 API/Web 不列入首轮 GPU 迁移。它们要么不使用当前 PyTorch 路径，要么在实测流水线中的成本很低。

## 主机前置条件

- 安装与 Docker Engine 匹配的 NVIDIA Container Toolkit，并完成 Docker runtime 配置。
- 在修改项目镜像前，必须先让一个已有本地镜像通过 `--gpus all` 启动，并在容器内确认 `torch.cuda.is_available()`。
- CUDA PyTorch 版本必须通过 RTX 5060 Ti 的实际容器测试确定，不能只根据宿主机能运行 `nvidia-smi` 判断兼容。

## 验收标准

- 默认 `infra/compose.yaml` 仍能在纯 CPU 主机启动并完成 Basic Pitch 与实验引擎的既有测试。
- GPU override 启动后，Worker 健康检查或诊断命令同时报告 GPU 型号、PyTorch/CUDA 版本和 `torch.cuda.is_available() == True`。
- Demucs、GAME、torchcrepe 的 provenance 分别记录实际设备与耗时，不再使用笼统的 `worker-default`。
- 使用同一输入分别运行 CPU/GPU，音符、F0 帧数和人声 stem 满足既定等价容差；取消任务仍能终止模型子进程。
- 分阶段报告墙钟耗时、CPU 使用、峰值显存和加速比。若某阶段 GPU 没有稳定收益或发生显存不足，该阶段保持 CPU。

## 回退方案

GPU 镜像、Compose override 和设备配置均保持可选。删除 override 或设置 `VSS_INFERENCE_DEVICE=cpu` 即回到现有 CPU 路径，不迁移数据库数据，也不改变默认转录引擎。

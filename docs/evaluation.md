# 转录质量评测

评测以人工标注的音符事件为基准，执行一对一匹配，分别报告“音高 + 起音”和“音高 + 起止”两套 precision、recall、F1，以及平均起止误差。默认音高容差 50 cents、起音容差 50 ms，止音容差为 `max(50 ms, 参考时值的 20%)`。

```bash
python scripts/evaluate-transcription.py \
  packages/test-fixtures/evaluation/reference.json \
  packages/test-fixtures/evaluation/prediction.json
```

批量评测使用已登记 manifest，并把所有模型和处理阶段放在同一容差下比较：

```bash
python scripts/evaluate-transcription-manifest.py \
  evaluation/manifest.json \
  --output evaluation/reports/baseline.json
```

定位整理和量化损失时，导出原始、整理后、量化后音符及每项删除、合并和冲突原因：

```bash
python scripts/diagnose-transcription.py raw-notes.json diagnostics.json \
  --bpm 120
```

消融参数包括 `--disable-pitch-range`、`--disable-continuity`、`--disable-stitching`、`--disable-quantization`、`--keep-quantization-conflicts`、最短时值和最低置信度。默认配置固定在 `evaluation/baseline-config.json`，未经记录不得在候选模型之间改变。

GAME 参数诊断使用 `scripts/run-game-tuning-sweep.sh`。网格和选择规则固定在 `evaluation/game-tuning-grid.json`，runner 通过 manifest 的 singer-disjoint split 只读取 tuning 音频。若 tuning 门槛失败，不运行调参后的 holdout；逐片段和 runtime 继续保存在 Git 忽略的 `data/evaluation/vocadito-results/`。

`evaluation/manifest.json` 当前只有 CC0 合成 fixture，用于验证工具本身，不含第三方录音。`evaluation/reports/synthetic-baseline.json` 和 `synthetic-diagnostics.json` 不是实际歌曲质量报告。

Vocadito（Bittner、Pasalo、Bosch、Meseguer Brocal、Rubinstein，DOI `10.5281/zenodo.5578807`，CC BY 4.0）下载到 `data/evaluation/vocadito/` 后，可用 Docker Worker 复现真实孤立人声基线：

```bash
python scripts/prepare-vocadito.py data/evaluation/vocadito
docker compose -f infra/compose.yaml run --rm --no-deps \
  -e PYTHONPATH=/workspace/workers/transcription:/workspace/apps/api \
  -v "$PWD:/workspace:ro" \
  -v "$PWD/data/evaluation/vocadito:/dataset:ro" \
  -v "$PWD/data/evaluation/vocadito-results:/results" \
  worker python /workspace/scripts/run-basic-pitch-benchmark.py \
  /dataset/Audio /results --skip-existing
python scripts/prepare-vocadito.py data/evaluation/vocadito
python scripts/evaluate-transcription-manifest.py \
  evaluation/vocadito-manifest.json \
  --output evaluation/reports/vocadito-basic-pitch.json
```

固定划分与结果见 `evaluation/vocadito-manifest.json` 和 `evaluation/reports/vocadito-baseline.md`。下载音频、转换标注、逐段诊断和模型运行明细留在 `data/`，不会进入 Git。

GAME 与 SOME 的 P1 对比使用独立镜像，不修改生产 Worker。权重按 `docs/model-licenses.md` 的目录和哈希准备后运行：

```bash
bash scripts/run-vocadito-candidates.sh
```

脚本会核对权重、准备固定 commit 源码归档、构建 CPU 实验镜像、运行三个候选并生成统一报告。当前结果见 `evaluation/reports/vocadito-candidate-comparison.md`；没有候选通过全部预登记门槛，不能据此更换默认引擎。

真实片段须遵循[转录标注规范](transcription-annotation.md)，按歌曲和歌手隔离调参集与保留测试集。公开仓库只提交确认允许再分发的音频和标注；私有授权材料只在 manifest 保存本机相对引用，不进入 Git。达到 `quality_gate` 前不得更换默认引擎。

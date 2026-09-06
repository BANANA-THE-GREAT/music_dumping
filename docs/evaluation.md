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

`evaluation/manifest.json` 当前只有 CC0 合成 fixture，用于验证工具本身，不含第三方录音。`evaluation/reports/synthetic-baseline.json` 和 `synthetic-diagnostics.json` 不是实际歌曲质量报告。

真实片段须遵循[转录标注规范](transcription-annotation.md)，按歌曲和歌手隔离调参集与保留测试集。公开仓库只提交确认允许再分发的音频和标注；私有授权材料只在 manifest 保存本机相对引用，不进入 Git。达到 `quality_gate` 前不得更换默认引擎。

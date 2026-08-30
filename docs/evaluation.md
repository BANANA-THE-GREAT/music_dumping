# 转录质量评测

评测以人工标注的音符事件为基准，执行音高一致、起音与结束时间在容差内的一对一匹配，报告 precision、recall、F1、平均起音误差和平均结束误差。

```bash
python scripts/evaluate-transcription.py \
  packages/test-fixtures/evaluation/reference.json \
  packages/test-fixtures/evaluation/prediction.json
```

默认起音容差 50 ms、结束容差 100 ms，可通过 `--onset-ms` 和 `--offset-ms` 修改。fixture 是 CC0 合成标注，不包含第三方录音。

当前 fixture 只验证评测工具本身，不能证明真实歌曲质量。Beta 发布前应加入按 2/4、3/4、4/4、6/8、男女声音域、干声/混音和不同伴奏密度分层的人工标注集合，并单独保存浏览器基线与后端模型报告。

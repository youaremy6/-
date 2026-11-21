# eval/lanzhou — 兰州话评测集（P0）

> 当前状态：**尚未采集真实录音，`results.csv` 全部为空**。本目录是可直接执行的评测脚手架，不含伪造分数。

## 目的

用真实兰州话录音回答三个问题，而不是用演示者自己的声音自证：

1. 兰州话 ASR 的字符错误率（CER）是否 < 30%（spec 9.2）？
2. 译文“意思保留”母语者评分是否 ≥ 4/5？
3. 反向 TTS 的“能否听懂”≥ 4/5、“像不像兰州话”≥ 3/5（spec 3B）？

## 目录

```text
eval/lanzhou/
  metadata.csv        # 30 条：3 位说话人 × 10 句，含参考文本与采集状态
  results.csv         # CER 与人工评分结果（当前为 not_run 模板）
  run_eval.py         # 计算 CER、合并人工评分
  make_metadata.py    # 从预设句生成 metadata.csv
  audio/              # 录音素材（不入库；见 audio/README.md）
  transcript/         # 参考转写与人工校对记录
```

## 采集要求

- 至少 3 位说话人，**不要全部用演示者本人**；年龄段与性别尽量分开。
- 每位说话人 10 句，覆盖就医 4 句、出行 3 句、买卖 3 句（`make_metadata.py` 已按这个比例生成）。
- 每题一句，安静环境，手机外放距离 20–30 cm；建议直接用小程序录音，导出 16 kHz 单声道 PCM。
- 每题对应 `metadata.csv` 的 `audio_path`，填好 `duration_s`、`age_band`、`gender`、`consent`。
- 参考文本 `ref_text` 必须由母语者校对后再用于打分；draft 文本上的 CER 只能作为参考。

## 运行

```bash
# 1) 采集并转写后，生成 hypothesis.csv（列：item_id,text）
#    可用 scripts/probe_asr.py 或正式 ASR 链路批量产出

# 2) 计算 CER
python eval/lanzhou/run_eval.py --hypothesis hypothesis.csv

# 3) 三位听者打分后合并（列：item_id,meaning_score,tts_intelligibility,tts_authenticity）
python eval/lanzhou/run_eval.py --hypothesis hypothesis.csv --scores scores.csv
```

脚本在缺少 hypothesis 时只写空模板并打印 `not_run`，不会编造 CER。

## 判定

| 指标 | 通过线 | 未通过时的动作 |
|---|---|---|
| CER | < 30% | 降低 ASR 承诺；只保留文字 + 预设句，标注“识别不可靠” |
| 意思保留 | 平均 ≥ 4/5 | 加回译确认；低置信度不自动播放 |
| TTS 可懂度 | 平均 ≥ 4/5 | 反向只保留文字 + 语音包，不宣称实时方言 TTS |
| TTS 像不像 | 平均 ≥ 3/5 | 不宣称“像兰州人说话”，只写“方言化表达” |

## 当前诚实结论

- 没有真实录音，**CER 未知**；不得对外宣称“高准确率”。
- 预设句里的兰州话文本是草稿，未经母语者校对；`assets/phrases/phrases.json` 中全部为 `draft`。
- 兰州话音频是占位合成（普通话音色朗读），不能当作方言语音样本。

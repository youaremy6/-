# recordings/ — 母语者录音（替换占位音频的唯一入口）

把兰州话母语者的录音按 **phrase id** 命名放进这里，再运行：

```powershell
python scripts/build_phrases.py
```

构建脚本会优先使用这里的文件，把它们复制到 `audio/lanzhou/`，并把
`phrases.json` 里的 `kind` 从 `placeholder` 改成 `recorded`；小程序里
“示意音频，待母语者录制”的标记会自动消失。

## 命名

```text
recordings/
  lanzhou/
    medical_01.wav     # 也可以 .mp3
    medical_02.mp3
    ...
  mandarin/            # 可选：普通话真人录音
    medical_01.wav
```

id 列表见 `assets/phrases/phrases.source.json`（27 条，如 `medical_01`、`transport_03`、`market_06`、`help_01`）。

## 格式要求

- **WAV**：16 kHz、单声道、16-bit PCM；时长 0.5–20 秒。
- **MP3**：建议 32–64 kbps 单声道；时长 0.5–20 秒。
- 安静环境、单人、一句一条；不要背景音乐、不要多人对话。
- 手机录的 m4a/aac 不能直接放进来，先转格式：

```powershell
ffmpeg -i phone.m4a -ar 16000 -ac 1 -c:a pcm_s16le recordings/lanzhou/medical_01.wav
```

（没有 ffmpeg 时，用任意工具导出为 16k 单声道 WAV 即可。）

## 校对与同意

- 录音只解决“声音”，**文本仍需母语者逐条校对**。校对完成后把
  `phrases.source.json` 里对应条目的 `reviewStatus` 改为 `verified`，再重新构建。
- 每条录音都要有同意记录，填 `consent.csv`（说话人、日期、用途）。
  未取得书面同意的声音不得使用；不得使用公众人物、未成年人或第三方声音。
- 音频会随小程序包发布（离线可用）。替换后需要重新上传/发布小程序版本才会生效；
  如果希望“上传后立即生效、无需发版”，需要改成服务端下发音频 URL（见 README 第 5 节末尾）。

## 构建行为

- 有录音：用录音，`kind=recorded`。
- 没录音、已有音频：保留现有文件（不会每次重建都重新合成）。
- 没录音、也没有音频：生成占位（普通话 TTS 朗读方言文本）。
- `--force` 只影响“生成占位”，**不会覆盖** `recordings/` 里的录音。
- `python scripts/build_phrases.py --check` 会校验录音格式并报告哪些还是占位/草稿。

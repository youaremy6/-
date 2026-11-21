# 语音包状态

- 兰州话：7 条母语者录音，20 条占位。
- `audio/mandarin/`：本地 TTS 合成或普通话录音，仅作演示示例。
- 占位音频由普通话音色朗读兰州话文本生成，**不是**兰州话母语者录音。
- 替换方式：把母语者录音放到 `recordings/lanzhou/<phrase_id>.wav`（16 kHz 单声道 16-bit）或 `.mp3`，再运行 `python scripts/build_phrases.py`。
- 发布前还需由母语者校对文本，并把 `phrases.source.json` 的 `reviewStatus` 改为 `verified`。

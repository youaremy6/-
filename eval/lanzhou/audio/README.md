# audio/ — 评测录音

把真实录音放在这里，按 `metadata.csv` 的 `audio_path` 命名：

```text
audio/
  S1/medical_01.pcm
  S1/medical_02.pcm
  S2/transport_01.pcm
  ...
```

要求：

- 16 kHz、单声道、16-bit、裸 PCM（或 WAV）。
- 每题一句，0.8–30 秒；不要裁剪到听不清开头。
- 录音前取得说话人同意：仅用于本项目评测，不用于训练，可随时要求删除。
- 音频文件默认不入库（体积与隐私原因）；需要版本化时使用对象存储并保留删除记录。

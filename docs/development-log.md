# 小甘 · 赛期开发记录

> 记录用于原创核验与复现，不包含海报设计文件。日期按本机开发会话整理；提交到 GitHub 后，以 commit 时间为准。

## 2026-11-21 · 范围与后端

- 确定 P0：兰州话 ↔ 普通话、半双工单句、3 个场景 + 日常常用句。
- 明确边界：只做兰州话（试运行），不做全甘肃、不做实时同传、不承诺准确率。
- 搭建 FastAPI BFF：
  - 音频校验：16 kHz / 单声道 / 16-bit PCM/WAV，0.8–30 秒。
  - 编排：ASR → 结构化翻译 → TTS；失败降级到文字与常用句。
  - 缓存、幂等、HMAC 签名媒体 URL、删除记录。
- 建立测试：音频校验、翻译、健康检查、隐私、讯飞参数、H5 页面。
- 产出：`server/app/`、`server/tests/`、`docs/api.md`、`README.md`。

## 2026-11-21 · 小程序与常用句

- 原生微信小程序 3 页：对话、常用句、设置。
- 显式状态机、按住录音、重说/改字/切换方向、权限与切后台处理。
- 常用句 27 条（就医 7 / 出行 7 / 买卖 6 / 日常 7），54 个音频。
- 7 条用户真人录音（组撒、没麻达、攒劲、干散、瓜怂、日厌、坏怂）接入；
  其余 20 条为占位音，文本标记 draft。
- 产出：`miniprogram/`、`assets/phrases/`、`scripts/build_phrases.py`。

## 2026-11-21 · H5 试用与链路验证

- `GET /demo`：浏览器录音 → 16 kHz WAV → 同一套 API；文字反译与常用句。
- 增加麦克风环境自检、“测试后端上传（不需要麦克风）”、错误提示。
- 用 headless Chrome + fake mic 验证录音上传链路；用小程序静态检查与 wx stub 页面仿真验证交互。
- 产出：`server/app/static/demo.html`、`scripts/verify_h5.py`、`scripts/simulate_miniprogram.mjs`。

## 2026-11-21 · 识别问题定位与修复

- 现象：录音转写总是“请问公交车站在哪”。
- 定位：当时是 `MockASR`，只哈希 PCM 前 2048 字节（64 ms）；按住说话开头是静音，
  全 0 哈希固定命中第 10 条 `transport_04`。
- 修复：按 20 ms 帧做能量检测，跳过开头静音，从有声段取 16 KB 哈希；
  全静音返回空，前端提示“没听清”。
- 产出：`server/app/services/asr_mock.py`、对应 pytest。

## 2026-11-21 · 接入本地真实 ASR

- 新增 `WhisperASR`：`faster-whisper small`，CPU int8，输入 16 kHz PCM。
- 用常用句构造 `initial_prompt`，减少“没麻达/干散/瓜怂”等被转成普通话同音词。
- `/health` 增加 `asr=whisper/local`；模型不可用时自动退回 mock。
- 实测：`没麻达 → 没麻达`（0.855）、`干散 → 干散`、`组撒 → 组撒`；
  `攒劲/日厌/坏怂` 仍可能错，说明通用小模型对兰州话的边界。
- 产出：`server/app/services/asr_whisper.py`、`server/requirements.txt`、`.env.example`。

## 2026-11-21 · 公网演示与配置

- 使用 Cloudflare 临时隧道暴露 H5：
  `https://kentucky-wage-elections-organizing.trycloudflare.com/demo`
- 修正 `PUBLIC_BASE_URL`，使签名音频 URL 指向公网域名。
- 小程序 `API_BASE` 从 `127.0.0.1` 改为当前公网地址；真机仍需 request 合法域名。
- 产出：`miniprogram/config.js`、`server/app/static/demo.html`、`README.md`。

## 可复现命令

```powershell
python -m pip install -r server/requirements-dev.txt
python -m pytest server/tests -q          # 71 passed
node scripts/check_miniprogram.mjs        # MINIPROGRAM STATIC CHECK OK
python scripts/smoke_test.py
python -m uvicorn app.main:app --app-dir server --host 127.0.0.1 --port 8000
```

## 未完成 / 下一步

- 讯飞甘肃话 ASR、CosyVoice3、LLM 真实凭据未配置，未做真机点验。
- 30 条评测集尚未采集录音，CER/可懂度无数字。
- 本地 Whisper 是通用中文模型，不是甘肃话专用；要求稳定方言准确率时接讯飞。

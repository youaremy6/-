# 技术探针结果（P0）

> 时间：2026-11-21 · 环境：Windows 11 / Python 3.12.10 / FastAPI 0.165.0
> 结论先行：**两个探针都没有在真实供应商上执行**（本机没有讯飞凭据、没有 CosyVoice3 GPU 服务、没有母语者参考音频与书面同意），因此按 spec 3 的要求**降级**，而不是拿模拟结果冒充真实能力。

## 0. 一览

| 项目 | 状态 | 证据 | 降级动作 |
|---|---|---|---|
| 探针 A：讯飞甘肃话 ASR | **未执行**（缺 `XF_APP_ID`/`XF_API_KEY`/`XF_API_SECRET`/`XF_ACCENT_GANSU`） | `server/tests/` 69 项测试 + `scripts/smoke_test.py` 只证明 mock 链路可用 | 默认 mock ASR：从预设句里确定性选一句；小程序顶部显示“演示模式”横幅 |
| 探针 B：CosyVoice3 兰州话 TTS | **未执行**（无 GPU 服务、无参考音频、无同意记录） | `assets/phrases/audio/` 54 个文件（27 条普通话合成 + 27 条兰州话：7 条用户录音 + 20 条占位） | 只播预设语音包；任意文本仅返回文字并提示“方言语音暂时没生成” |
| 兜底语音包 | **已完成（含明确占位）** | 27 条 × 2 语言 = 54 个音频，约 920 KB，已打进小程序包 | 20 条兰州话音频标记 `kind=placeholder`；`help_01~07` 为用户提供的真人录音 |

**关键诚实声明**

- mock ASR **不是语音识别**。它按请求音频的哈希从 27 条预设句里挑一句，用于把整条链路跑通。
- 兰州话音频 **不是母语者录音**。它由普通话音色（`zh-CN-XiaoxiaoNeural`）朗读兰州话文本生成，只保证离线演示有声音可放。
- 因此当前版本的 CER、TTS 可懂度/像不像，**全部未知**，不得对外宣称准确率。

---

## 1. 探针 A：兰州话 ASR

### 目标与通过标准（spec 3A）

- 用 15–30 秒、16 kHz 单声道 PCM 的兰州话录音，拿到可用中文转写。
- 通过标准：3 段不同说话人的日常句子中，至少 2 段能让听者读懂原意。
- 参数要求：`sampleRate: 16000`、`numberOfChannels: 1`、`format: 'PCM'`、`duration: 30000`、`audioMode: 'voiceRecognition'`；服务端 `domain: 'xfime-mianqie'`，`accent` 必须来自控制台变量 `XF_ACCENT_GANSU`。

### 实际执行情况

| 项 | 结果 |
|---|---|
| 供应商连通 | 未执行（无凭据） |
| 3 段不同说话人 | 未执行（无录音） |
| 原始转写 / 耗时 / 空结果率 / 明显错字 | 无数据，不填写 |
| 通过与否 | 未判定 |

### 已完成的工程准备

- `server/app/services/asr_xfyun.py`：按讯飞 IAT WebSocket 协议实现签名、分帧（1280 B / 40 ms）、`wpgs` 增量结果合并；`accent` 缺失时拒绝进入 live 模式（**没有硬编码假值**）。
- `scripts/probe_asr.py`：吃 3 个录音文件，输出原始转写、耗时、空结果，并写 JSON；缺凭据时明确 `SKIPPED` 并返回码 2。
- `server/app/api/routes_health.py`：`/api/v1/health` 会显示 `asr.mode=mock|live|misconfigured`，演示前可一眼确认。

### 复跑步骤

1. 在讯飞控制台开通流式听写与甘肃话/方言能力，读取 accent 参数。
2. 在 `.env` 填写 `XF_APP_ID`、`XF_API_KEY`、`XF_API_SECRET`、`XF_ACCENT_GANSU`。
3. 采集 3 位说话人的 15–30 秒 PCM（`eval/lanzhou/audio/S1/*.pcm`）。
4. `python scripts/probe_asr.py eval/lanzhou/audio/S1/*.pcm --out eval/lanzhou/probe_asr_results.json`
5. 3 位听者逐条判断“能否读懂原意”，把结论写回本文件；未达 2/3 就维持降级。

---

## 2. 探针 B：兰州话 TTS

### 目标与通过标准（spec 3B）

- 用一份**书面同意**的兰州话母语者参考音频（≤30 秒、安静、单人、内容与合成文本不同）。
- `CosyVoice3 inference_instruct2`，指令 `You are a helpful assistant. 请用甘肃话表达。<|endofprompt|>`。
- 3 位听者给“能否听懂”和“像不像兰州话”打 1–5 分。
- 通过标准：可懂度平均 ≥ 4/5，像不像平均 ≥ 3/5；否则反向只保留文字 + 预设语音包。

### 实际执行情况

| 项 | 结果 |
|---|---|
| CosyVoice3 服务 | 未执行（无 GPU 服务地址） |
| 参考音频 + 同意记录 | 没有；不能拿公众人物或未授权声音替代 |
| 10 句合成 | 未执行 |
| 可懂度 / 像不像 | 无数据 |
| 通过与否 | 未判定 |

### 已完成的工程准备

- `server/app/services/tts_cosyvoice.py`：multipart 调 `/inference_instruct2`（`tts_text`、`instruct_text`、`prompt_wav`），把无头 PCM 包成 WAV；超时/空音频映射为可降级的错误。
- TTS 降级链：`cosyvoice3` → 预设语音包 → 纯文字。**不会伪造语音**。
- `scripts/probe_tts.py`：10 句日常普通话，输出到 `eval/lanzhou/tts_probe/` 和 manifest；缺配置时 `SKIPPED`。
- 预设包音频生成脚本：`scripts/build_phrases.py`（`edge-tts` 优先，Windows SAPI 兜底）。

### 复跑步骤

1. 找一位兰州话母语者，签署“仅用于本项目、可撤回、不训练公开音色”的书面同意。
2. 录 ≤30 秒参考音频，配 `COSYVOICE_PROMPT_TEXT`。
3. 启动 CosyVoice3 FastAPI 服务，填写 `COSYVOICE_BASE_URL`、`COSYVOICE_PROMPT_AUDIO_URL`。
4. `python scripts/probe_tts.py`
5. 3 位听者盲听打分，写回本文件；低于阈值就维持降级。

---

## 3. 兜底语音包（已完成）

| 项 | 值 |
|---|---|
| 条数 | 27（就医 7 / 出行 7 / 买卖 6 / 日常 7） |
| 文件 | 54 个音频（普通话 27 + 兰州话 27：7 条真人录音 + 20 条占位），约 920 KB |
| 服务端位置 | `assets/phrases/audio/` |
| 小程序离线位置 | `miniprogram/assets/phrases/audio/`（随包发布） |
| 数据文件 | `assets/phrases/phrases.json` → 生成 `miniprogram/data/phrases.js` |
| 校对状态 | 27/27 为 `draft`，**未**经母语者校对 |
| 兰州话音频 | 7 条 `recorded`（`help_01~07`，用户提供的“组撒/没麻达/攒劲/干散/瓜怂/日厌/坏怂”录音），20 条 `placeholder` |
| 普通话音频 | 本地 `edge-tts` 合成示例，仅用于演示，不是真人录音 |

已验证：断网时小程序仍能加载常用句并播放本地音频（静态检查确认 54 个文件都在包内，路径存在）；后端 `GET /api/v1/phrases` 也能返回可播放 URL。

**必须补的动作**：母语者重录剩余 20 条 `audio/lanzhou/`，校对文本，把 `reviewStatus` 从 `draft` 改为 `verified`。未完成前，UI 会一直显示“草稿 · 待母语者校对”；占位音频还会显示“示意音频”。

---

## 4. 因为探针未过而生效的降级清单

| 能力 | 当前行为 |
|---|---|
| 兰州话识别 | mock：按音频哈希选预设句；结果带 `mock_asr` 警告；小程序顶部黄色横幅 |
| 语义转写 | mock：优先预设句对照表，其次 19 条保守词表；不确定词降置信度 |
| 普通话→兰州话 | LLM mock 改写；有预设音频就播，否则只给文字 |
| 兰州话→普通话 | 音频来自预设包（普通话侧）；任意文本只给文字 |
| TTS | 只播预设包；不生成新音频，避免“听起来像”的假象 |
| 验收指标 | CER / 意思保留 / TTS 评分全部标记“未测”，不得引用为成绩 |

## 5. 证据索引

- 后端测试：`server/tests/`（69 passed）
- 端到端冒烟：`scripts/smoke_test.py`（health → phrases → 双向翻译 → 签名音频 → 删除记录）
- 小程序静态检查：`scripts/check_miniprogram.mjs`（3 页面、handler、状态机、54 个音频文件）
- 小程序页面仿真：`scripts/simulate_miniprogram.mjs`（用 `wx` API stub 驱动真实页面代码，跑通录音→上传→结果→改字→反向输入→常用句→设置删除；并因此发现并修复了“上传过早返回导致 uploading→ready 非法状态”的竞态）
- 网页 H5 验证：`scripts/verify_h5.py`（headless Chrome + fake microphone，真实浏览器录音 → 16k WAV → 上传 → 结果卡；已跑通）
- 评测脚手架：`eval/lanzhou/`（30 条 metadata，CER 工具，`results.csv` 为 not_run）

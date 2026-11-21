# API 说明（P0）

Base URL 默认 `http://127.0.0.1:8000`，接口前缀 `/api/v1`。
所有请求体均为 UTF-8；`POST /translate/audio` 用 `multipart/form-data`，其余用 `application/json`。

> P0 不做用户注册与鉴权，**只用于本地演示/内网试用**。公网部署前必须加网关鉴权、限流和 HTTPS。

## 0. 通用约定

### 请求头

| Header | 说明 |
|---|---|
| `X-Request-Id` | 可选；不传则服务端生成，响应会回显同名字段，便于排查 |
| `X-Mock-Behavior` | **仅 dev**：`asr_empty` / `asr_low` / `tts_error` / `llm_error`，用于失败注入 |
| `X-Mock-Asr-Text` | **仅 dev 且 ASR 为 mock**：指定 mock 转写文本，方便演示固定句子 |

`ENV=prod` 时两个模拟头自动失效。

### 错误结构

```json
{
  "error": {
    "code": "too_short",
    "message": "太短了，按住多说一会儿（至少 0.8 秒）。",
    "retryable": false,
    "details": {}
  }
}
```

| code | HTTP | 含义 | 客户端动作 |
|---|---|---|---|
| `invalid_request` | 400 | 参数格式不对（含 requestId 规则） | 修正后重试 |
| `unsupported_dialect` | 400 | 不是 `lanzhou` | 提示只支持兰州话 |
| `invalid_scenario` | 400 | 场景不是 medical/transport/market/help | 回退为不选场景 |
| `unsupported_direction` | 400 | 文本接口方向错误 | 检查请求 |
| `empty_audio` | 400 | 0 字节 | 重录 |
| `audio_too_large` | 413 | 超过 2 MB | 分句说 |
| `unsupported_audio` | 415 | 非 16k 单声道 16-bit PCM/WAV（如 mp3） | 重录 |
| `too_short` | 422 | < 0.8 秒 | 提示“按住多说一会儿” |
| `too_long` | 422 | > 30 秒 | 提示“一次说一句” |
| `asr_empty` | 422 | 没识别到文字 | 重说或改文字 |
| `low_confidence` | 422 | 置信度低于 `ASR_MIN_CONFIDENCE`，不进入翻译；`details.asrText` 可回填编辑框 | 改字或重说 |
| `asr_timeout` / `asr_network_error` | 504 / 502 | 讯飞不可用 | 保留录音，重试上传 |
| `llm_*` | 502/504 | 真实 LLM 出错 | 服务端已降级为原文 + 警告，通常不会返回 |
| `record_not_found` | 404 | 记录不存在/已删 | 清理本地记录 |
| `media_forbidden` | 403 | 签名过期或错误 | 重新请求结果 |
| `media_not_found` | 404 | 音频已过期 | 重新生成 |
| `phrase_pack_unavailable` | 503 | 语音包未加载 | 检查 `assets/phrases/phrases.json` |
| `internal_error` | 500 | 未预期错误 | 提示重试/用常用句 |

### 结果警告（`warnings` 数组）

| warning | 含义 |
|---|---|
| `mock_asr` | 转写来自内置语料，不是真实识别 |
| `low_confidence` | 置信度处于“可翻译但需确认”区间（0.45–0.7） |
| `llm_degraded` | LLM 失败，直接使用原文 |
| `tts_error` | 语音合成失败，只返回文字 |
| `text_only` | 降级路径，只返回文字 |
| `numbers_changed` | 改写后数字/金额/剂量缺失；文字保留，但要求确认 |
| `cached_phrase` | 音频来自预设语音包 |
| `idempotent_replay` | 同一 requestId 的重复请求，返回缓存结果 |

---

## 1. `POST /api/v1/translate/audio`

兰州话录音 → 普通话文字 + 普通话语音。

`multipart/form-data`：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `audio` | file | 是 | 16 kHz 单声道 16-bit PCM 或 WAV；0.8–30 秒；≤ 2 MB |
| `dialectId` | string | 是 | P0 固定 `lanzhou` |
| `requestId` | string | 是 | 6–64 位 `[A-Za-z0-9_-]`，幂等 ID |
| `scenario` | string | 否 | `medical` / `transport` / `market` / `help` |

请求示例：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/translate/audio \
  -F "audio=@sample.pcm;type=application/octet-stream" \
  -F "requestId=req_demo_0001" \
  -F "dialectId=lanzhou" \
  -F "scenario=medical"
```

成功响应：

```json
{
  "requestId": "req_demo_0001",
  "direction": "dialect_to_mandarin",
  "asrText": "大夫，我脑壳有点晕。",
  "normalizedText": "医生，我有点头晕。",
  "translatedText": "医生，我有点头晕。",
  "outputText": "医生，我有点头晕。",
  "outputAudioUrl": "http://127.0.0.1:8000/media/9f2c...c1.mp3?exp=1763700000&sig=...",
  "confidence": 0.86,
  "cached": false,
  "warnings": ["mock_asr", "cached_phrase"],
  "needsConfirmation": false,
  "latencyMs": 42
}
```

说明：

- `confidence = min(ASR 置信度, LLM meaningConfidence)`。
- ASR 置信度 < 0.45 → 422 `low_confidence`，不翻译。
- ASR 置信度 0.45–0.7 → 200，但带 `low_confidence`、`needsConfirmation=true`，客户端不自动播放。
- LLM 失败 → 200，`llm_degraded`，`normalizedText = asrText`，置信度 ≤ 0.35。
- 数字/金额/剂量在改写后缺失 → `numbers_changed` + `needsConfirmation=true`（文字照常返回，不会静默吞掉）。
- TTS 失败 → 200，`tts_error`，`outputAudioUrl=null`，文字仍保留。

---

## 2. `POST /api/v1/translate/text`

普通话文本 → 兰州话文字 + 兰州话语音 + 回译。

```json
{
  "requestId": "req_demo_0002",
  "direction": "mandarin_to_dialect",
  "dialectId": "lanzhou",
  "scenario": "medical",
  "text": "医生，我有点头晕。"
}
```

字段：`text` 1–200 字符；`direction` 必须是 `mandarin_to_dialect`；`dialectId` 必须是 `lanzhou`。

成功响应：

```json
{
  "requestId": "req_demo_0002",
  "direction": "mandarin_to_dialect",
  "inputText": "医生，我有点头晕。",
  "dialectText": "大夫，我脑壳有点晕。",
  "backTranslation": "医生，我有点头晕。",
  "outputText": "大夫，我脑壳有点晕。",
  "outputAudioUrl": "http://127.0.0.1:8000/media/9f2c...c1.mp3?exp=1763700000&sig=...",
  "ttsProvider": "phrase_pack",
  "confidence": 0.9,
  "cached": false,
  "warnings": ["cached_phrase"],
  "needsConfirmation": false,
  "latencyMs": 8
}
```

降级：

1. CosyVoice3 → 2. 预设语音包 → 3. 纯文字（`tts_error` / `text_only`）。
   “普通话兜底”需要第二个 TTS 供应商，P0 未配置，因此不做假音频。

---

## 3. `POST /api/v1/translate/dialect-text`（P0 扩展，用于“改字”）

用户改完 ASR 转写后，重新规范化并合成，不重录音频。

```json
{
  "requestId": "req_demo_0003",
  "dialectId": "lanzhou",
  "scenario": "medical",
  "text": "大夫，我脑壳有点晕。"
}
```

响应：

```json
{
  "requestId": "req_demo_0003",
  "direction": "dialect_to_mandarin",
  "inputText": "大夫，我脑壳有点晕。",
  "normalizedText": "医生，我有点头晕。",
  "translatedText": "医生，我有点头晕。",
  "outputText": "医生，我有点头晕。",
  "outputAudioUrl": "...",
  "ttsProvider": "phrase_pack",
  "confidence": 0.92,
  "cached": false,
  "warnings": ["cached_phrase"],
  "needsConfirmation": false,
  "latencyMs": 9
}
```

为什么需要它：spec 4.1/7.4 要求低置信度可“改字”，而 `translate/text` 只定义了反方向；
这个扩展让“改正兰州话转写 → 重新出普通话”成为真实链路，而不是只改显示。

---

## 4. `GET /api/v1/phrases?scenario=medical`

返回预设句、双语文本、音频 URL、校对状态。

```json
{
  "dialectId": "lanzhou",
  "count": 7,
  "draftCount": 7,
  "notice": "预设句为草稿文本，需经兰州话母语者校对后才能作为正式内容发布。",
  "reviewPolicy": "...",
  "phrases": [
    {
      "id": "medical_01",
      "scenario": "medical",
      "mandarin": "医生，我有点头晕。",
      "lanzhou": "大夫，我脑壳有点晕。",
      "reviewStatus": "draft",
      "note": "待校对：'脑壳'是否为兰州话日常说法，需母语者确认。",
      "mandarinAudio": {
        "url": "http://127.0.0.1:8000/assets/phrases/audio/mandarin/medical_01.mp3",
        "kind": "generated",
        "voice": "zh-CN-XiaoxiaoNeural"
      },
      "lanzhouAudio": {
        "url": "http://127.0.0.1:8000/assets/phrases/audio/lanzhou/medical_01.mp3",
        "kind": "placeholder",
        "voice": "zh-CN-XiaoxiaoNeural（占位，非母语者朗读）"
      }
    }
  ]
}
```

`reviewStatus` 只有 `verified` 能作为正式内容；`draft` 必须显示草稿标记。
`kind=placeholder` 表示不是母语者录音。

---

## 5. `GET /api/v1/health`

演示前检查依赖，不泄露任何密钥。

```json
{
  "status": "degraded",
  "version": "0.1.0",
  "env": "dev",
  "dialect": "lanzhou（试运行）",
  "dependencies": {
    "asr": {"ok": true, "provider": "mock", "mode": "mock", "detail": "未配置讯飞 ASR 凭据，使用内置演示转写（不是真实识别）。"},
    "llm": {"ok": true, "provider": "mock", "mode": "mock", "detail": "未配置 LLM，使用内置词表改写（草稿）。"},
    "tts": {"ok": true, "provider": "mock", "mode": "mock", "detail": "未配置 CosyVoice3，只播放预设语音包；其他文本仅返回文字。"},
    "storage": {"ok": true, "provider": "local-media", "mode": "live"},
    "phrases": {"ok": true, "provider": "phrase-pack", "mode": "live"}
  },
  "limits": {
    "maxAudioBytes": 2000000,
    "maxRecordSeconds": 30,
    "minRecordSeconds": 0.8,
    "maxTextChars": 200,
    "asrMinConfidence": 0.45,
    "asrHintConfidence": 0.7,
    "signedUrlTtlSeconds": 3600,
    "outputAudioTtlMinutes": 60,
    "phraseCount": 27,
    "phraseVersion": "0.1.0"
  },
  "privacy": "录音只用于本次翻译，处理完即删除；日志不记录原文、译文和音频；..."
}
```

`status`：全部 live → `ok`；有 mock 但都可用 → `degraded`；有依赖不可用 → `error`。

---

## 6. `GET /media/{key}?exp=...&sig=...`

播放服务端生成的语音。HMAC 签名，TTL 默认 1 小时、上限 24 小时；过期或签名错误返回 403。

## 7. `DELETE /api/v1/records/{requestId}`

删除本次记录及生成语音（供设置页“删除我的本次记录”）。成功返回：

```json
{"deleted": true, "requestId": "req_demo_0001"}
```

原话/译文本来就不落库；这里删除的是生成的音频与幂等缓存。

---

## 8. 缓存、幂等与隐私

- 音频缓存键：`sha256("lanzhou|" + VOICE_ID + "|" + mode + "|" + normalizedText + "|" + LLM_INSTRUCT_VERSION)`；命中直接复用已生成音频。
- 幂等：按“端点 + requestId”缓存 1 小时；重复提交返回同一结果（`cached=true`）。
- 同一 requestId 的并发请求用进程内锁串行化，避免重复计费。
- 日志只记录 `request_id / method / path / status / duration_ms / error code`，**不记录**原文、译文、音频。
- 输入音频只在临时内存中处理；输出音频落本地媒体目录，按 `OUTPUT_AUDIO_TTL_MINUTES` 清理。
- 签名密钥来自 `MEDIA_SIGNING_SECRET` / `STORAGE_SECRET_KEY`；未配置时使用仅限开发的固定派生值，**生产必须配置**。

## 9. 环境变量

完整列表与说明见仓库根目录 `.env.example`。关键项：

| 变量 | 说明 |
|---|---|
| `PROVIDER_MODE` | `auto`（默认）/ `mock` / `live` |
| `PUBLIC_BASE_URL` | 生成签名 URL 的外部地址，真机必须是可访问的 https |
| `XF_ACCENT_GANSU` | 讯飞甘肃话 accent，必须从控制台读取 |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI 兼容接口 |
| `COSYVOICE_BASE_URL` / `COSYVOICE_PROMPT_AUDIO_URL` | CosyVoice3 与参考音频 |
| `MAX_AUDIO_BYTES` / `MAX_RECORD_SECONDS` | 上传限制 |
| `AUDIO_RETENTION_HOURS` | `0` 表示不保留原始录音 |

## 10. 网页试用页（非 API 合约）

`GET /demo` 返回服务端自带的 H5 试用页：浏览器 `getUserMedia` 录音 → 转 16 kHz WAV → 调
`POST /api/v1/translate/audio`；也支持文字反译和常用句播放。页面本身不保存任何数据，
鉴权方式与 API 相同（P0 无鉴权）。源码：`server/app/static/demo.html`。

# 讯飞甘肃话 ASR 接入路径（逐步）

> 目标：让 `/api/v1/translate/audio` 从 `mock` 切到真实的讯飞语音听写，能识别兰州话录音。
> 官方文档：[语音听写（流式版）WebAPI](https://www.xfyun.cn/doc/asr/voicedictation/API.html)
> 本项目的实现：`server/app/services/asr_xfyun.py`

## 0. 最短路径（先看这 8 步）

1. 注册/登录讯飞开放平台，完成实名认证。
2. 控制台创建一个 **WebAPI** 应用。
3. 给应用添加 **语音听写（流式版）** 服务（领免费额度或购买套餐）。
4. 在「语音听写（流式版）→ 方言/语种」里添加 **甘肃话**；页面会显示该方言的参数值。
5. 复制应用的 **AppID、APIKey、APISecret**。
6. 把这四个值填进 `.env` 的 `XF_APP_ID`、`XF_API_KEY`、`XF_API_SECRET`、`XF_ACCENT_GANSU`。
7. 重启后端，`/api/v1/health` 里 `dependencies.asr.mode` 应变成 `live`。
8. 录一段 16k PCM 或跑 `python scripts/probe_asr.py 你的录音.wav` 验证转写。

## 1. 注册与实名认证

- 打开 https://www.xfyun.cn/ 注册/登录。
- 控制台：https://console.xfyun.cn/
- 按提示完成实名认证（个人或企业）。未认证通常无法领取/购买语音服务。

## 2. 创建应用

控制台 → **我的应用** → **创建新应用**：

| 字段 | 建议填法 |
|---|---|
| 应用名称 | `xiaogan-lanzhou`（随意） |
| 应用平台 | **WebAPI** |
| 应用领域 | 按实际选，教育/生活服务均可，不影响 ASR |

创建后进入应用详情，后面会用到 AppID。

## 3. 添加“语音听写（流式版）”

两条路都可以：

- 产品页：https://www.xfyun.cn/services/voicedictation → 立即使用/领取免费额度；
- 或在控制台应用详情 → **服务管理/添加服务** → 找到 **语音听写（流式版）** → 添加。

添加后确认：

- 服务状态为“已开通/试用中”；
- 有可用额度（免费额度或套餐）。额度用完会报错。

> 我们的代码使用 `domain: "xfime-mianqie"`（方言免切），它属于语音听写（流式版）下的能力，必须在控制台开通/授权。

## 4. 开通“甘肃话”方言

官方文档写明：方言免切支持 23 种方言，包括 **甘肃话**；但**方言需要在控制台单独添加/购买**，未授权会报 `11200`。

路径（控制台版本可能微调）：

```text
控制台 → 语音听写（流式版） → 方言/语种 → 添加“甘肃话” → 试用/购买
```

添加成功后，页面上会**显示该方言对应的参数值**（这就是 `accent`）。把它原样复制到：

```env
XF_ACCENT_GANSU=控制台显示的那个值
```

⚠️ 不要猜 `gansu`、`ganyu` 之类的值。代码不会硬编码，值不对会报 11200 或识别异常。

## 5. 拿 AppID / APIKey / APISecret

控制台 → 我的应用 → 选择应用 → **服务接口认证信息**（有的版本叫“API 密钥”）：

| 控制台字段 | `.env` 变量 |
|---|---|
| AppID | `XF_APP_ID` |
| APIKey | `XF_API_KEY` |
| APISecret | `XF_API_SECRET` |

三者都是 32 位字符串。**不要提交到仓库，不要放进小程序。**

## 6. 填 `.env` 并重启

在仓库根目录：

```powershell
Copy-Item .env.example .env   # 如果还没有
notepad .env
```

至少填：

```env
PROVIDER_MODE=auto
XF_APP_ID=你的AppID
XF_API_KEY=你的APIKey
XF_API_SECRET=你的APISecret
XF_ACCENT_GANSU=控制台显示的甘肃话参数值
XF_DOMAIN=xfime-mianqie
XF_ASR_TIMEOUT_SECONDS=30
```

重启后端（先停掉旧进程）：

```powershell
python -m uvicorn app.main:app --app-dir server --host 127.0.0.1 --port 8000
```

检查：

```powershell
curl.exe -s http://127.0.0.1:8000/api/v1/health
```

期望看到：

```json
"asr": {"ok": true, "provider": "xfyun", "mode": "live"}
```

如果还是 `mock`，说明四个变量没读全；如果是 `misconfigured`，看 `detail`。

## 7. 用真实兰州话验证

### 方式 A：项目自带探针

```powershell
python scripts/probe_asr.py eval/lanzhou/audio/S1/medical_01.pcm
```

要求：16 kHz、单声道、16-bit PCM（或 WAV），1–30 秒。脚本会打印原始转写、耗时、空结果，并写 JSON。

### 方式 B：H5 / 小程序录音

- H5：`http://127.0.0.1:8000/demo`，按住说一句；
- 小程序：开发者工具里按住说话（需勾选“不校验合法域名”）。

### 方式 C：curl

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/translate/audio `
  -F "audio=@test.wav;type=audio/wav" `
  -F "requestId=req_xf_0001" `
  -F "dialectId=lanzhou" `
  -F "scenario=medical"
```

看返回里的 `asrText` 是否接近你实际说的话。

## 8. 常见错误与排查

| 现象/错误码 | 原因 | 处理 |
|---|---|---|
| `11200` | 方言/服务未授权 | 按第 3、4 步开通语音听写 + 甘肃话；确认额度 |
| `10005` | AppID 授权失败 | AppID 填错，或该应用没添加听写服务 |
| `10006` / `10007` | 采样率等参数非法 | 必须是 16k（或 8k）、16-bit、单声道；不要传 mp3 给方言 |
| `10009` | 输入数据非法 | 检查 base64/分帧；我们是 1280 B/帧 |
| `10014` / `10019` | 会话超时 | 30 秒内说完；网络稳定；超时后重试 |
| `10163` | 单帧音频过大 | 代码已用 1280 B/帧，一般不会触发 |
| health 仍 `mock` | `.env` 没被读到 / 缺变量 | 确认在仓库根目录启动，或设置系统环境变量 |
| health `misconfigured` | 四个变量缺一个 | 四个都要有，包括 `XF_ACCENT_GANSU` |
| 一直转圈/超时 | 服务器出网被限制 | ECS/本机需能访问 `iat-api.xfyun.cn:443` |

> 官方文档还说明：方言场景的 mp3 支持有限，**优先 PCM**；单次听写最长 1 分钟；默认 50 路并发。

## 9. 只接 ASR 时，哪些能力会真的工作？

| 环节 | 只配 `XF_*` 后 |
|---|---|
| 兰州话 → 文字 | ✅ 真实讯飞识别 |
| 文字规范化/翻译 | ⚠️ 仍是 mock 词表（要配 `LLM_*` 才真翻译） |
| 普通话 → 兰州话文字 | ⚠️ mock 改写（要配 `LLM_*`） |
| 方言语音合成 | ⚠️ 只播预设语音包（要配 `COSYVOICE_*`） |

所以：**接 ASR 只解决“听懂你说什么”**；要完整双向，还需要 LLM 和 TTS。验收时不要把三者混为一谈。

## 10. 安全与费用

- `.env` 已在 `.gitignore`；不要提交真实密钥，不要截图泄露。
- 免费额度/套餐按讯飞控制台为准；额度用完调用会失败。
- 不要把 AppID/APIKey/APISecret 放进小程序或前端页面。
- 如果密钥泄露，立刻在控制台重置。

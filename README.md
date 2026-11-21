# 小甘 · 兰州话 ↔ 普通话对话卡

微信小程序 + FastAPI 后端。按住说一句兰州话，松开得到普通话文字和语音；输入普通话，得到兰州话文字和语音。两位使用者共用一部手机，在**就医 / 出行 / 买卖**三个场景完成一次信息交换。

> **只支持兰州话（试运行）**，不是“全甘肃方言”。本版是半双工单句对话，不做实时同传。
>
> **当前 ASR**：优先使用本地 `faster-whisper small` 做真实识别；模型或依赖不可用时自动退回 mock。LLM 与 CosyVoice3 仍需凭据，未配置时走演示链路。真实能力、评测数据与真机验证状态见 [`docs/limitations.md`](docs/limitations.md) 和 [`docs/spikes.md`](docs/spikes.md)。

---

## 1. 现在能跑什么

| 能力 | 状态 |
|---|---|
| FastAPI 后端：录音校验、ASR/LLM/TTS 编排、缓存、幂等、签名音频、删除记录 | ✅ 71 项测试通过 |
| 微信小程序：3 个页面、显式状态机、错误分支、权限、切后台、常用句全屏 | ✅ 静态检查 + 页面级仿真（未真机点验） |
| 网页试用（H5）：浏览器录音、文字反译、常用句 | ✅ `GET /demo` 已实现；已用 headless Chrome + fake mic 跑通“录音→WAV→上传→结果卡” |
| 27 条双语预设句（就医 7 / 出行 7 / 买卖 6 / 日常 7）+ 54 个音频 | ✅ 可离线播放；7 条日常为用户提供的真人录音，其余 20 条仍是占位；文本为 **draft** |
| 讯飞甘肃话 ASR / CosyVoice3 / LLM 真实链路 | ⚠️ 代码已接，但**未用真实凭据验证**；本地 Whisper 已可做通用中文真实识别 |
| 评测集 CER / 可懂度 / 像不像 | ⚠️ 脚手架就绪，**尚未采集录音，无数字** |
| 微信开发者工具 + 真机 | ⚠️ 未在本环境执行，需你按第 4 节操作 |

## 2. 目录

```text
miniprogram/              # 原生 WXML/WXSS/JS，无构建链
  pages/index/            # 对话页：方向、场景、按住说话、结果卡、改字
  pages/phrases/          # 常用句：分类、播放、全屏“给对方看”
  pages/settings/         # 设置：语速、自动播放、隐私、删除记录
  utils/                  # api / recorder / audio / state / settings
  data/phrases.js         # 由脚本生成，离线常用句数据
  assets/phrases/audio/   # 离线语音包
server/                   # FastAPI BFF
  app/api/                # translate / phrases / health / media / records
  app/services/           # xfyun / whisper / mock ASR、OpenAI 兼容 LLM、CosyVoice3、缓存、存储
  tests/                  # 71 项 pytest
  Dockerfile
assets/phrases/           # phrases.source.json + phrases.json + audio/
eval/lanzhou/             # 30 条评测 metadata、CER 工具、results 模板
scripts/                  # 构建语音包、探针、冒烟、静态检查
docs/                     # spikes / api / demo / limitations
```

## 3. 后端快速开始

要求 Python 3.11+（已在 3.12.10 验证）。

```powershell
# 仓库根目录
python -m pip install -r server/requirements-dev.txt

# 可选：复制配置（不填密钥也能启动；ASR 优先本地 Whisper，LLM/TTS 回退演示）
Copy-Item .env.example .env

# 可选但推荐：先下载本地 Whisper small 模型（约 500 MB）
python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"

# 启动
python -m uvicorn app.main:app --app-dir server --host 127.0.0.1 --port 8000
```

验证：

```powershell
python scripts/smoke_test.py
# health: degraded asr=whisper llm=mock tts=mock phrases=27
# 没有下载模型时会显示 asr=mock
# ...
# SMOKE OK
```

- Swagger：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/v1/health
- 接口细节：[`docs/api.md`](docs/api.md)

### 从 mock 切到真实供应商

在 `.env` 填写对应变量即可，`PROVIDER_MODE=auto` 会自动启用：

0. **本地 Whisper ASR（无需讯飞凭据）**：默认 `WHISPER_MODEL=small`，模型缓存在
   `~/.cache/huggingface/hub`。模型存在时 `/health` 显示 `asr=whisper/local`；缺失时自动退回 mock。
   `medium` 更准但更慢、更占内存。它是一般中文模型，不是甘肃话专用。
1. **讯飞甘肃话 ASR**：`XF_APP_ID` / `XF_API_KEY` / `XF_API_SECRET` / `XF_ACCENT_GANSU`。
   `XF_ACCENT_GANSU` 必须从讯飞控制台开通后读取，**不要猜**；为空时 live ASR 自动关闭。
   控制台的完整申请路径（创建应用 → 添加语音听写（流式版）→ 方言/语种添加“甘肃话” → 取密钥 → 验证）见
   [`docs/xfyun-setup.md`](docs/xfyun-setup.md)。
2. **LLM（OpenAI 兼容）**：`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`。
3. **CosyVoice3**：`COSYVOICE_BASE_URL` + 母语者书面同意的参考音频 `COSYVOICE_PROMPT_AUDIO_URL`（≤30 秒）。

改完重启后端，`/api/v1/health` 的 `mode` 应变为 `live`。

### 让别人用浏览器试用（H5，最快）

后端自带网页试用页 `GET /demo`（源码：[server/app/static/demo.html](server/app/static/demo.html)）：浏览器麦克风录音 →
转成 16 kHz WAV → 调同一套 API；也有文字输入和常用句播放，不依赖微信。

![网页试用页](docs/demo-h5-512.png)

- 本机打开：`http://127.0.0.1:8000/demo`
- 别人试用：浏览器麦克风要求 **HTTPS**（localhost 例外）。最省事的是临时隧道：

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

拿到 `https://xxx.trycloudflare.com` 后，把 `.env` 的 `PUBLIC_BASE_URL` 改成它并**重启后端**，
分享 `https://xxx.trycloudflare.com/demo`，或用任意二维码工具把该链接转成二维码。
（ngrok 同理；正式部署时用你的 https 域名。）

- 微信内置浏览器可能拒绝麦克风权限，让对方用系统浏览器（Safari / Chrome）打开；
  没有麦克风时页面仍可用文字输入和常用句。
- 页面会显示**麦克风环境自检**（HTTPS / 浏览器支持 / 微信内置浏览器），并提供
  “测试后端上传（不需要麦克风）”按钮：它能出结果就说明后端与上传链路正常，问题在麦克风权限。
- 页面会读 `/api/v1/health`；ASR 为 `mock` 时显示“演示模式”，为 `whisper/local` 时显示“录音会先做本地识别”。

## 4. 在微信开发者工具打开

1. 安装[微信开发者工具](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html)。
2. 「导入项目」→ 目录选 `miniprogram/` → AppID 可先用测试号（`project.config.json` 里是 `touristappid`）。
3. 「详情 → 本地设置」勾选 **不校验合法域名**（本地 `http://127.0.0.1:8000` 需要）。
4. 后端已启动后编译；首屏应显示“小甘 / 兰州话 ↔ 普通话 · 试运行”。
5. 首次按住说话会弹出麦克风用途说明；拒绝后仍可进入常用句。

### 真机 / 云托管

- 真机不能用 `127.0.0.1`：把 `miniprogram/config.js` 的 `API_BASE` 改成云托管或已备案的 `https://` 域名。
- 小程序用的是 `wx.request` + `wx.uploadFile`，因此需要在微信后台把该域名加入 **request 合法域名** 与 **uploadFile 合法域名**（或改用 `callContainer` 并相应改 `utils/api.js`）。
- 服务端 `PUBLIC_BASE_URL` 必须与真机可访问的地址一致，否则返回的签名音频 URL 打不开。
- 云托管部署（构建上下文是仓库根目录，语音包要一起进镜像）：

```bash
docker build -f server/Dockerfile -t xiaogan-server .
docker run --rm -p 8000:8000 --env-file .env xiaogan-server
```

### 分享给别人试用（小程序二维码）

- 开发者工具「预览」生成的二维码**只有开发者/项目成员**能扫，不能发给外部评委。
- 想让别人用：需要真实 AppID；在小程序后台把对方加成**体验成员**，上传代码后把该版本设为体验版，分享体验版二维码。
- 想让任何人都能用：必须提交审核并发布，之后才有正式小程序码。
- `touristappid` 只能本地调试，不能上传/发布。
- 如果只是几个人快速试用，直接用上面的 `/demo` H5 链接或二维码，不必走审核。

## 5. 预设句与语音包

源文件：`assets/phrases/phrases.source.json`（文本、场景、校对状态、备注）。

```powershell
# 重新生成 phrases.json + 缺失音频 + 小程序离线副本（已有音频会复用，不重复合成）
python scripts/build_phrases.py

# 强制重新合成所有占位音频（不会覆盖 recordings/ 里的真人录音）
python scripts/build_phrases.py --force

# 只检查资源是否齐全（不写文件）
python scripts/build_phrases.py --check
```

### 用母语者录音替换兰州话占位音频

1. 把录音按 phrase id 放进 `assets/phrases/recordings/lanzhou/`：
   `medical_01.wav`、`transport_03.mp3`……（id 见 `phrases.source.json`）。
   WAV 要求 16 kHz、单声道、16-bit；也接受 MP3；每句 0.5–20 秒。
2. 运行 `python scripts/build_phrases.py`。
3. 脚本会：复制录音到 `audio/lanzhou/` → 把 `kind` 改成 `recorded` →
   `voice` 改成“兰州话母语者录音” → 重写 `miniprogram/data/phrases.js` 和离线音频。
4. 小程序里“示意音频，待母语者录制”的标记会自动消失（判断依据是 `kind === 'placeholder'`）。

完整说明与格式转换命令见 [`assets/phrases/recordings/README.md`](assets/phrases/recordings/README.md)。
未录音的条目继续保留占位音频，并在 `audioNotice` / `AUDIO_NOTICE.md` 里计数。

- 生成脚本优先用 `edge-tts`（需要网络），失败时回退 Windows SAPI（`lameenc` 转 MP3）。
- **普通话音频**默认是合成示例；如有真人录音，放进 `recordings/mandarin/` 即可替换。
- 所有文本默认 `reviewStatus=draft`。只有母语者逐条校对后才能改为 `verified`，否则只能作为草稿展示。
- 生成后会自动写入 `miniprogram/data/phrases.js` 并复制音频到 `miniprogram/assets/phrases/`，保证断网可用。
- **注意**：小程序的包内文件在运行时只读，替换录音后必须重新上传/发布小程序版本才会生效。
  若希望“上传后立刻生效、无需发版”，需要把常用句音频改为服务端下发 URL（`GET /api/v1/phrases` 已返回 URL），
  小程序启动时拉取并缓存；目前页面默认用包内离线音频，这一模式尚未接。

## 6. 测试与检查

```powershell
# 后端单元 + API 集成（含失败注入、隐私、幂等、签名）
python -m pytest server/tests -q

# 端到端冒烟（需要后端已启动）
python scripts/smoke_test.py

# 小程序静态检查（Node 18+；语法、页面文件、WXML handler、状态机、音频路径）
node scripts/check_miniprogram.mjs

# 小程序页面逻辑仿真（需要后端已启动）：用 wx API stub 驱动真实页面代码，
# 跑通 录音→上传→结果→改字→反向输入→常用句→设置删除
node scripts/simulate_miniprogram.mjs

# 网页 H5 录音链路验证（可选）：先按 scripts/verify_h5.py 顶部命令启动带 fake mic 的
# headless Chrome（CDP 端口 9231），再运行：
python scripts/verify_h5.py

# 技术探针（缺凭据时会明确 SKIPPED，不会伪造结果）
python scripts/probe_asr.py eval/lanzhou/audio/S1/*.pcm
python scripts/probe_tts.py
```

## 7. 跑评测

```powershell
python eval/lanzhou/make_metadata.py          # 从预设句生成 30 条计划
python eval/lanzhou/run_eval.py               # 无 hypothesis 时写空模板并打印 not_run
python eval/lanzhou/run_eval.py --hypothesis hypothesis.csv --scores scores.csv
```

评测要求 3 位说话人 × 10 句，覆盖就医/出行/买卖，不要全用演示者本人。指标与判定见 [`eval/lanzhou/README.md`](eval/lanzhou/README.md)。

## 8. 隐私与安全

- 录音只用于本次翻译；原始音频不落库，处理完即删（`AUDIO_RETENTION_HOURS=0`）。
- 日志只记录请求 ID、路径、状态码、耗时，不记录原话、译文、音频。
- 生成语音的签名链接默认 1 小时过期（上限 24 小时）；设置页可“删除我的本次记录”。
- 不把用户音频用于训练；不克隆公众人物/未成年人/未授权声音。
- 小程序里没有任何 API Key；密钥只在服务端环境变量。
- P0 没有鉴权与限流，**不要直接暴露公网**；上线前加网关鉴权、限流与 HTTPS。

## 9. 验收对照（spec 9.1）

| 项 | 状态 |
|---|---|
| 微信开发者工具可启动，无控制台报错 | ⚠️ 未在本环境执行（无开发者工具）；页面/语法已静态检查 |
| 真机完成兰州话→普通话闭环 | ⚠️ 未执行；需真实 ASR 凭据 + 真机 |
| 真机完成普通话→兰州话闭环 | ⚠️ 未执行；mock 下可用预设句验证交互 |
| 3 场景各 ≥4 条、共 ≥12 条，双语 + 音频 | ✅ 27 条、54 个音频（含“日常”7 条）；20 条方言音频占位、7 条真人录音；文本 draft |
| 任意失败都有可操作提示，不无限 loading | ✅ 已实现，pytest 覆盖 asr_empty/low_confidence/tts_error/网络失败/重复点击 |
| 切后台/来电后停止录音与播放 | ✅ 已实现（`onHide`/`onUnload`/中断监听）；⚠️ 未真机验证 |
| 权限拒绝后仍可用常用句 | ✅ 已实现 |
| 设置页隐私说明 + 删除本次记录 | ✅ 已实现，pytest 覆盖删除 |
| 9.2 质量目标（CER/TTS 评分） | ⚠️ 未采集，无数字 |
| 9.3 90 秒演示脚本 | ✅ 已写（含 mock 版诚实脚本）；未彩排 10 次 |

## 10. 文档

- [`docs/spikes.md`](docs/spikes.md)：两个技术探针的真实状态与降级决定
- [`docs/xfyun-setup.md`](docs/xfyun-setup.md)：讯飞甘肃话 ASR 的逐步接入路径与错误码
- [`docs/api.md`](docs/api.md)：接口、错误码、缓存/幂等、隐私
- [`docs/demo.md`](docs/demo.md)：3 分钟 / 90 秒演示脚本与失败分支
- [`docs/limitations.md`](docs/limitations.md)：能力边界、风险、上线前 checklist
- [`eval/lanzhou/README.md`](eval/lanzhou/README.md)：评测集协议

## 11. 一句话

> 小甘先解决兰州话与普通话的双人现场沟通：按住说一句，马上看到两种文字并听到对应语音；实时合成失败时自动退回常用句语音包，让不会说兰州话的人也能把事说清楚。

# 提交到 GitHub 的文件清单

> 本仓库是微信小程序 + FastAPI 后端。海报设计文件不提交。

## 一、应该提交

| 路径 | 内容 |
|---|---|
| `README.md` | 项目说明、运行方式、能力边界 |
| `.env.example` | 环境变量模板（无密钥） |
| `.gitignore` | 已忽略 `.env`、运行时媒体、缓存、微信私有配置 |
| `miniprogram/` | 小程序源码、页面、`data/phrases.js`、离线音频 |
| `server/app/` | FastAPI 代码、H5 页面、provider、路由 |
| `server/tests/` | 71 项 pytest |
| `server/requirements.txt` / `requirements-dev.txt` | 依赖 |
| `server/Dockerfile` | 后端容器 |
| `server/conftest.py` | 测试入口 |
| `assets/phrases/` | 27 条文本、54 个音频、7 条真人录音 |
| `scripts/` | 构建语音包、探针、冒烟、静态检查、H5 验证 |
| `docs/` | API、H5、限制、spikes、讯飞配置、开发记录 |
| `eval/lanzhou/` | 30 条评测 metadata、CER 工具与结果模板 |

`miniprogram/project.config.json` 可以提交，里面的 AppID 是公开标识；如果不想暴露，改成
`touristappid` 或占位值。

## 二、不要提交

| 路径 | 原因 |
|---|---|
| `assets/poster/`、根目录 `一只甘肃的鸟_小甘.png` | 海报设计文件，按你的要求排除 |
| `.env`、`server/.env` | 可能含密钥 |
| `server/var/` | 运行时生成的临时音频，不应进仓库 |
| `__pycache__/`、`.pytest_cache/` | Python 缓存 |
| `miniprogram/project.private.config.json` | 微信开发者工具私有配置 |
| `node_modules/`、`.venv/`、`venv/` | 依赖目录 |
| `*.log`、临时截图 | 运行产物 |
| 任何 `API_KEY` / `API_SECRET` / token | 只放 `.env` |

## 三、开发记录怎么保留

仓库里已经包含：

- `docs/development-log.md`：按阶段记录范围、后端、小程序、H5、mock 问题、Whisper 接入、公网演示。
- `docs/spikes.md`：技术探针与决策。
- `docs/limitations.md`：能力边界、未验证项、风险。
- `docs/api.md`、`docs/demo.md`、`docs/xfyun-setup.md`：接口与接入过程。
- `server/tests/`：71 项测试，直接反映迭代。
- `assets/phrases/recordings/lanzhou/`：7 条真人录音，是音频迭代证据。
- `eval/lanzhou/`：评测集 metadata 与工具。

建议再用 Git 提交历史保留过程，例如：

```powershell
git init
git add .
git commit -m "feat: 小甘 P0 - 小程序 + FastAPI + 本地 Whisper ASR"
git branch -M main
git remote add origin <你的仓库地址>
git push -u origin main
```

如果分阶段提交，可以按：

1. `feat: backend skeleton + 71 tests`
2. `feat: miniprogram 3 pages + phrase pack`
3. `feat: H5 demo + fake mic verification`
4. `fix: skip leading silence in mock ASR`
5. `feat: local Whisper ASR with Lanzhou prompt`
6. `docs: development log + limitations`

## 四、提交前检查

```powershell
python -m pytest server/tests -q          # 71 passed
node scripts/check_miniprogram.mjs        # MINIPROGRAM STATIC CHECK OK
python scripts/smoke_test.py
```

确认没有：

```text
.env
server/var/
__pycache__/
.pytest_cache/
miniprogram/project.private.config.json
assets/poster/
一只甘肃的鸟_小甘.png
```

`miniprogram/config.js` 里的 `API_BASE` 现在是临时 Cloudflare 地址。正式提交时换成你的
HTTPS 域名；如果保留临时地址，隧道过期后会连不上。

# PublishFlow

本地优先的多平台内容发布工作台，版本 **0.5.0**。产品以发布为主角、编辑为配角，内容、账号凭证、任务队列、审计记录与平台数据都保存在自己的设备上。

阶段 5 在既有「本地处理 → 草稿保存 → 多平台账号 → 持久化队列 → 定时与周期调度 → 审计回执」闭环上，增加全量写操作审计、执行时合规复核、本地数据看板与合规指标回采，并补齐容器部署、便携打包和 CI。发布前加固进一步引入授权内容快照、调度授权指纹、幂等键和不确定提交保护。

## 获取源码

```bash
git clone https://github.com/jiangzai37/PublishFlow.git
cd PublishFlow
```

Windows 也可以直接下载 ZIP 后解压。仓库不包含 `.env`、账号 Cookie、数据库、上传文件或本地密钥。

## 已实现

- FastAPI + Vue 3 + TypeScript + SQLite 本地工作台
- OpenAI 兼容模型接入，可切换 DeepSeek、通义、Ollama 等兼容网关
- 本地图片/视频素材库，支持上传、标签、筛选与随机选取；封面与视频自动登记，被草稿引用的素材受删除保护
- 可选 OpenAI 兼容模型生图，仅接受 base64 图片并保存到本地
- 自定义排版模板，内置模板不可修改，支持实时预览；预览、定时任务与实际发布共用数据库模板渲染器
- CSDN、知乎独立草稿复用，可选模型平台适配，原稿保持不变，不自动发布
- 1200 × 630 程序化封面合成，支持自定义背景图
- 视频上传、时长与尺寸校验、拖拽预览、抽帧封面、H.264 / AAC MP4 兼容转码
- 视频标题、简介、标签、B 站分区与合集设置，独立视频草稿和投稿确认流程
- CSDN、知乎、B 站 Cookie 导入，Fernet 本地加密，登录态验证
- Playwright 可见浏览器发布，平台选择器独立配置，按内容类型自动匹配适配器
- 按目录自动发现的平台适配器注册机制
- SQLite 持久化任务队列，暂停、恢复、跳过与安全自动重试
- 发布幂等键与活动任务去重，避免响应丢失或重复点击创建多个投稿任务
- 授权时冻结标题、正文、标签、渲染 HTML 和媒体指纹；后续编辑不会改变已授权任务内容
- 调度计划绑定内容授权指纹，草稿、模板或媒体变化后自动失效，必须重新确认
- APScheduler 一次性定时、5 段 Cron 周期计划、多账号错峰与重启恢复
- 周期执行幂等保护，服务中断后结果不确定的任务必须人工确认
- 发布前内容归属确认、敏感内容拦截、广告法风险提示
- 持久化合规决策，记录内容 SHA-256、规则版本、命中项与确认状态；实际发布和重试前再次校验
- 结构化操作审计，覆盖 API 写操作与队列状态变化；请求正文、查询字符串、请求头、Cookie 和密钥不会入库
- 本地数据看板，提供周期任务、成功率、平台分布、发布节奏与内容数据汇总
- 指标回采仅支持手工录入、平台官方导出或授权 API；按任务和日期去重，同一来源重复录入会更新旧快照

## 环境要求

- Windows 10/11、macOS 或 Linux
- Python 3.12+，推荐使用 [uv](https://docs.astral.sh/uv/)
- Node.js 22+
- 真实发布需要 Playwright Chromium 和可交互的图形桌面
- 视频处理优先使用系统 FFmpeg；未安装时使用依赖包内置 FFmpeg，元数据探测优先使用系统 ffprobe

## 快速启动

### Windows

双击 `start.bat`。脚本会检查依赖、按 `.env` 启动前后端并打开工作台。

首次使用发布功能前安装浏览器：

```powershell
.venv\Scripts\python.exe -m playwright install chromium
```

### macOS / Linux

```bash
bash scripts/start.sh
```

首次使用发布功能前安装浏览器：

```bash
.venv/bin/python -m playwright install chromium
```

启动脚本从项目根目录的 `.env` 读取 `APP_HOST`、`APP_PORT`、`FRONTEND_HOST` 和 `FRONTEND_PORT`。开发模式默认后端 `127.0.0.1:8765`、前端 `127.0.0.1:5173`。

### 本地生产模式

先构建前端，再由 FastAPI 同时提供页面与 API：

```bash
npm --prefix frontend ci
npm --prefix frontend run build
.venv/Scripts/python.exe scripts/serve.py
```

macOS / Linux 使用 `.venv/bin/python scripts/serve.py`。默认访问 `http://127.0.0.1:8765`，API 文档位于 `/docs`。

## Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
```

访问 `http://127.0.0.1:8765`。`.env` 中的 `HOST_PORT` 控制宿主机映射端口，容器内部固定监听 8765；Compose 只绑定宿主机回环地址，不直接暴露到局域网。SQLite、媒体文件和上传背景分别保存在 `publishflow_data` 与 `publishflow_uploads` 命名卷中。服务默认通过 `ALLOWED_HOSTS` 拒绝非本机 Host 请求，降低 DNS 重绑定风险；跨站写请求也会被拒绝。这些措施不等于远程身份认证，本应用没有登录系统，不要将端口反向代理或转发到公网，也不要将 `APP_HOST` 改为 `0.0.0.0` 后在不可信网络中运行。

```bash
docker compose logs -f publishflow
docker compose down
```

`docker compose down` 不会删除命名卷。只有确认不再需要本地数据时，才执行 `docker compose down -v`。

**容器部署边界**：镜像提供 Web、API、素材管理、看板、审计与持久化队列，但不安装可见浏览器。镜像与 Compose 默认设置 `PUBLISHING_ENABLED=false`，API、worker、队列恢复和调度执行都会拒绝真实发布，已有等待任务会安全标记失败、启用计划会停用，界面也会显示禁用原因。真实发布请使用带有图形桌面和 Playwright Chromium 的本机模式；容器模式也不应绕过平台验证。

## 便携打包

```bash
.venv/Scripts/python.exe scripts/package.py
```

macOS / Linux 使用 `.venv/bin/python scripts/package.py`。脚本执行前端干净安装与生产构建，在 `release/` 生成 `publishflow-0.5.0-portable.zip`。压缩包包含源码、CI、部署文件、脚本和已构建前端，不包含 `.env`、`.venv`、`node_modules`、数据库、Cookie、上传文件或测试产物。

解压后安装依赖并启动生产服务：

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r backend/requirements.txt
.venv/bin/python scripts/serve.py
```

Windows 对应使用 `.venv\Scripts\python.exe`。便携包不内置 Python、Node.js 或 Playwright 浏览器。

## 配置

复制 `.env.example` 为 `.env`。所有外部密钥只从本机环境变量读取，不会打包到前端。

```dotenv
MODEL_BASE_URL=https://api.openai.com/v1
MODEL_API_KEY=你的密钥
MODEL_NAME=gpt-4o-mini
```

可选模型生图使用独立配置，三项齐全后才启用：

```dotenv
IMAGE_BASE_URL=
IMAGE_API_KEY=
IMAGE_MODEL=
```

不配置模型也可以使用手动写作、示例内容、排版、封面、账号管理、看板和审计。生图接口仅接受 base64 图片，不下载响应中的远程图片地址。

合规与调度配置：

```dotenv
COMPLIANCE_ENABLED=true
COMPLIANCE_RULESET_VERSION=2026-11-26
SCHEDULE_TIMEZONE=Asia/Shanghai
MIN_PUBLISH_INTERVAL_SECONDS=90
MAX_RETRIES=1
RETRY_DELAY_SECONDS=120
```

关闭 `COMPLIANCE_ENABLED` 会停用内置敏感词与广告法规则，但内容归属确认和平台授权要求仍然保留。生产使用建议保持开启。

视频处理与上传限制：

```dotenv
FFMPEG_BIN=
FFPROBE_BIN=
MAX_VIDEO_UPLOAD_MB=4096
MAX_VIDEO_DURATION_SECONDS=14400
VIDEO_TRANSCODE_TIMEOUT_SECONDS=1800
VIDEO_UPLOAD_TIMEOUT_SECONDS=1800
```

`ENCRYPTION_KEY` 留空时会在数据目录创建本地密钥；POSIX 系统设置为 `0600`，Windows 通过 ACL 仅授予当前用户完全控制权限。请备份该密钥，否则已有 Cookie 凭证无法解密。视频文件仅接受上传目录中的本地文件，不开放任意路径读取。

## 导入平台账号

1. 在浏览器登录自己的 CSDN、知乎或 B 站账号。
2. 使用可信的 CookieJSON 浏览器扩展导出对应站点 Cookie。
3. 在工作台「账号与授权」选择平台、粘贴 JSON 并加密保存。
4. 点击「验证」确认登录态。

CSDN 接受 `csdn.net` 域 Cookie；知乎接受 `zhihu.com` 与 `zhimg.com` 域 Cookie；B 站接受 `bilibili.com` 与 `biliapi.net` 域 Cookie。Cookie 不会写入审计日志，也不会上传到任何第三方服务。请勿分享 Cookie 或包含 Cookie 的扩展导出文件。

## 素材、模板与一稿多发

1. 在「素材库」上传图片或视频、整理标签并筛选，点击「使用」后可作为文章封面或视频素材；也可按类型和标签随机选取。
2. 在「模板工坊」新建模板，或复制内置模板后调整字体、字号、颜色与间距，实时预览并保存；点击「应用模板」返回编辑台，也可在编辑台的「排版预设」中切换已保存模板。
3. 在文章编辑台点击「一稿多发」，选择复用至 CSDN 或知乎，按需勾选模型适配；核对并保存独立草稿后分别发布，不会自动投稿。

## 视频发布

1. 在「视频发布」新建视频草稿，上传 MP4、MOV、WebM、MKV 或 M4V 文件。
2. 填写标题、简介和标签，按需抽帧生成封面并转为发布兼容格式。
3. 选择已授权的 B 站账号、内容分区，可选填账号中已有的合集名称。
4. 选择立即投稿或定时投稿，确认内容归属与授权后提交。

视频任务与文章任务共用队列、调度和审计系统，但发布账号会按内容类型过滤。当前视频适配器以 B 站为首个落地平台，通过平台可见浏览器上传器传输大文件。抖音、视频号、快手、西瓜和 YouTube 尚未实现。平台页面发生变化时，更新 `publishers/selectors/bilibili.yaml` 即可调整选择器。真实投稿前应先用测试文件核对平台当前页面，并仅发布自己拥有版权或已获授权的内容。

## 数据看板与指标回采

- 「数据看板」支持近 7、30、90 天切换，展示任务量、成功率、平台分布、发布节奏、触达与互动数据。
- 只有状态为成功的任务可以录入指标，指标日期不能晚于今天。
- 数据来源限定为手工录入、平台官方导出和授权 API。系统不提供爬虫，不读取私密页面，不绕过平台限制。
- 同一任务、日期和来源重复提交会覆盖旧快照；统计时同一任务同一天的多个来源只计最新一份，避免重复累计。
- 指标是用户录入或授权回采的快照，不代表平台实时数据，也不保证各平台口径一致。

## 审计与合规

- 「发布记录」下方提供全量操作审计，可按结果和对象筛选，展开后查看请求 ID 与脱敏元数据。
- 所有 API 写操作和队列状态变化都会生成审计事件；GET 等只读请求不记录，以减少敏感数据暴露。
- 合规决策与任务在同一事务中保存。任务执行前重新计算内容指纹，禁止项会直接拦截，广告风险确认只对原内容有效。
- 创建任务时保存不可变发布快照。之后编辑草稿不会改变待发布内容；需要发布新版本时，请重新创建任务并确认授权。
- 定时计划保存授权指纹。草稿、模板或媒体变化会使 `authorization_valid=false`，计划在下次执行前停用并记录审计，不能靠旧授权发布新内容。
- 手动重试也会重新校验。内容在确认后发生变化，需要重新阅读并确认广告风险。
- 日志和审计仅保存在本地数据库，管理员仍应限制设备访问并定期备份。数据库中的审计是产品操作记录；Uvicorn、Playwright 等开发运行日志可能包含堆栈或本机路径，不应公开分享，也不属于审计数据。

## 发布与安全边界

- 只发布用户本人账号、用户拥有版权或有授权的内容，并遵守各平台机器人及自动化条款。
- 只有用户明确选择账号并确认授权后才会发布。
- 发布会打开本机 Playwright 浏览器。
- 遇到验证码、安全验证或页面结果不确定时，适配器会停止并提示人工检查，不处理验证、不规避风控。
- CSDN 适配器当前使用 Markdown 正文；知乎适配器将预览正文的纯文本写入富文本编辑区。
- 平台页面结构变化时，只需调整 `publishers/selectors/` 中对应 YAML，无需改发布流程。
- 自动重试只发生在适配器明确标记为可安全重试的失败上；结果不确定、验证挑战或可能已成功提交时不会自动重试。
- 视频上传准备阶段明确失败时可安全重试；点击投稿后的超时、中断或缺少成功回执均视为结果不确定，必须先在平台稿件管理中人工确认。
- 服务重启会把中断的 `running` 任务标记为需人工确认，不会盲目重复发布。
- 禁止批量虚假账号、养号、洗稿、抄袭搬运与绕过平台规则。

## 开发与 CI

```bash
# 后端测试与静态检查
cd backend
../.venv/Scripts/python.exe -m pytest -q
uvx ruff check app tests
uvx ruff format --check app tests
uvx pip-audit -r requirements.txt

# 前端类型检查与生产构建
cd ../frontend
npm run build

# 分别启动开发服务
cd ../backend
../.venv/Scripts/python.exe -m uvicorn app.main:app --reload
cd ../frontend
npm run dev
```

macOS / Linux 将 `.venv/Scripts/python.exe` 替换为 `.venv/bin/python`。后端测试使用临时数据目录，不会读写本机 `data/` 中的工作台数据库。

浏览器端到端验收会创建并删除测试草稿、账号、计划和媒体，**只能使用独立的一次性数据目录**。脚本拒绝项目真实 `data/` 和项目目录内的路径。先停止普通工作台服务，再按以下方式启动隔离服务并执行验收：

```bash
# Git Bash；macOS / Linux 请替换 Python 路径
export DATA_DIR="$TEMP/publishflow-smoke-data"
export UPLOAD_DIR="$TEMP/publishflow-smoke-uploads"
export PUBLISHFLOW_SMOKE_DATA_DIR="$DATA_DIR"
mkdir -p "$DATA_DIR" "$UPLOAD_DIR"
.venv/Scripts/python.exe scripts/serve.py &
npm --prefix frontend run dev -- --host 127.0.0.1 &
.venv/Scripts/python.exe scripts/smoke_test.py
```

端口或 API 地址不同时，用 `SMOKE_API_URL` 指定后端地址、`SMOKE_WEB_URL` 指定前端地址。测试产生的截图位于 `artifacts/`；不要将该脚本指向正在使用的数据目录。CI 同时使用空命名卷验证容器可写数据目录、草稿创建和真实发布禁用边界。

GitHub Actions 工作流位于 `.github/workflows/ci.yml`，分别执行后端测试与 Ruff、前端类型检查、依赖安全审计与构建、Playwright 桌面/平板/移动端浏览器回归，以及生产 Docker 镜像构建。浏览器回归覆盖保存竞态、独立授权、模板离开保护、弹窗焦点、移动导航、调度和视频流程，不会读取真实账号或发布内容，也不会推送镜像。

## 目录结构

```text
PublishFlow/
├─ backend/
│  ├─ app/api/              # REST 路由、指标导入与审计查询
│  ├─ app/storage/          # SQLite 模型、迁移与审计
│  ├─ app/auth/             # Cookie 校验与本地加密
│  ├─ app/queue_scheduler/  # 持久化队列、恢复与 APScheduler 调度
│  ├─ core/content_gen/     # 模型适配
│  ├─ core/typesetting/     # 排版渲染与预设
│  ├─ core/media/           # 封面合成与视频处理
│  ├─ core/compliance/      # 发布前与执行时合规检查
│  └─ publishers/           # 平台适配器与选择器
├─ frontend/                # Vue 3 工作台
├─ scripts/                 # 启动、生产服务、打包与浏览器验收
├─ .github/workflows/       # CI
├─ Dockerfile               # 单容器 Web + API 生产镜像
├─ docker-compose.yml       # 命名卷持久化部署
├─ .env.example             # 无密钥配置示例
├─ data/                    # 本地数据库与凭证密钥
│  ├─ assets/              # 素材库图片与视频
│  ├─ covers/              # 文章与视频封面
│  └─ videos/              # 上传与转码视频
├─ uploads/                 # 用户上传的封面背景
├─ artifacts/               # 本地验收截图，不纳入版本控制
└─ release/                 # 便携打包产物，不纳入版本控制
```

## 备份与迁移

停止服务后备份整个 `data/` 和 `uploads/`。其中 `data/.credential.key` 必须与 `data/publishflow.db` 一起保管；只恢复数据库而没有密钥时，账号 Cookie 无法解密。`.env` 中含有外部服务密钥，应单独加密保管，不要放入便携包或提交到仓库。

SQLite 使用 WAL 模式。复制数据库前先停止服务，或使用 SQLite 在线备份接口，避免遗漏尚未合并的 WAL 内容。

### 从旧版本升级

0.5.0 首次启动会自动为任务增加 `run_key`、`idempotency_key`、`snapshot_json`、`submission_uncertain` 字段，并为调度计划增加 `authorized`、`authorized_fingerprint` 字段，同时创建幂等键索引。升级前仍应先备份 `data/`、`uploads/` 和 `.env`。

- 旧任务没有快照时，为兼容历史记录仍按执行时的草稿内容发布；新建任务从 0.5.0 起始终使用授权快照。
- 旧调度计划没有授权指纹时会被安全停用，不能直接重新启用。请打开计划核对草稿、模板和媒体后重新授权。
- 旧版本无法理解新增的不确定提交状态。升级后不要降级运行服务，也不要在未核对平台稿件状态时重试历史任务。
- 数据库结构迁移只应新增字段和索引，不应删除用户数据；应用启动时自动执行，无需手工运行迁移命令。

## 许可证与安全问题

MIT License，详见 `LICENSE`。支持版本、私密漏洞报告方式和安全边界见 [`.github/SECURITY.md`](.github/SECURITY.md)。请勿在公开 Issue 中提交 Cookie、`.env`、凭证密钥、数据库或未脱敏的审计记录。

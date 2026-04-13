# VidPipe

> 热点抓取 → LLM文案 → ComfyUI视频生成 → 人工审核 → 抖音/小红书自动发布

基于 **n8n** 的全流程短视频生产线，所有 LLM 和 ComfyUI 调用封装在 Python Code 节点，支持本地模型（Ollama/vLLM）和云端模型（OpenAI/DeepSeek）无缝切换。

## 流水线

```
定时触发(6h) → 热点抓取 → LLM文案生成 → ComfyUI视频生成
    → 人工审核(Wait) → 发布抖音 + 发布小红书 → 结果汇总
```

## 目录结构

```
vid-pipe/
├── workflow.json         # n8n Workflow（导入 n8n UI）
├── docker-compose.yml    # 整栈编排
├── Dockerfile.n8n        # n8n 主节点（含 Python 环境）
├── Dockerfile.runner     # External Task Runner
├── .env.example          # 环境变量模板（复制为 .env 填写）
└── sau-backend/
    ├── Dockerfile        # social-auto-upload 服务
    └── server.py         # FastAPI 包装层
```

## 快速开始

### 1. 配置

```bash
cp .env.example .env
vim .env  # 填写 DB密码、n8n密钥、LLM配置、ComfyUI地址
```

### 2. 启动

```bash
docker compose up -d --build
```

### 3. 初始化平台 Cookie（首次必做）

在**宿主机**（有浏览器的环境）运行：

```bash
pip install social-auto-upload playwright
playwright install chromium

# 抖音登录（弹出浏览器扫码）
python -c "
import asyncio
from uploader.douyin_uploader.main import douyin_setup
asyncio.run(douyin_setup('./douyin_cookie.json', handle=True))
"

# 小红书登录
python -c "
import asyncio
from uploader.xhs_uploader.main import xhs_setup
asyncio.run(xhs_setup('./xhs_cookie.json', handle=True))
"

# 复制 cookie 到容器共享卷
docker cp douyin_cookie.json vidpipe-n8n-main:/data/cookies/douyin_cookie.json
docker cp xhs_cookie.json    vidpipe-n8n-main:/data/cookies/xhs_cookie.json
```

### 4. 导入 Workflow

1. 打开 http://localhost:5678
2. Workflows → Import from file → 选择 `workflow.json`
3. 激活 Workflow

## LLM 切换

修改 `.env` 中三个变量，重启即可：

| 场景 | LLM_BASE_URL | LLM_MODEL |
|---|---|---|
| 本地 Ollama | `http://host.docker.internal:11434/v1` | `qwen2.5:14b` |
| 本地 vLLM | `http://host.docker.internal:8000/v1` | `Qwen/Qwen2.5-14B` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |

## ComfyUI Workflow 替换

`workflow.json` 中 `ComfyUI视频/图像生成` 节点里的 `COMFY_WORKFLOW` 字典
是 SD1.5 基础 workflow，替换为你的实际 ComfyUI workflow JSON 即可。

## 注意

- Cookie 有效期约 7-30 天，到期后需重新登录
- sau-backend 使用 Playwright 模拟浏览器，需要宿主机或 VNC 环境扫码
- ComfyUI 需提前安装对应模型和自定义节点

# VidPipe — 热点→视频→抖音/小红书 全自动流水线

自动抓取微博/百度热搜，用 LLM 生成文案和提示词，ComfyUI + LTX-Video 2.3 Distilled 生成竖版短视频，人工审核后自动发布到抖音和小红书。

## 架构概览

```
┌──────────────────────────────────────────────┐
│  llm-01（主控节点）                            │
│  ├── n8n          :5678  流程编排              │
│  ├── n8n-runner          Python 执行器         │
│  ├── postgres     :5432  工作流状态存储         │
│  ├── sau-backend  :8080  抖音/小红书发布        │
│  └── vLLM         :8000  Gemma 4 27B IT       │
└──────────────────┬───────────────────────────┘
                   │ HTTP API
┌──────────────────▼───────────────────────────┐
│  llm-02（视频生成节点）                         │
│  └── ComfyUI      :8188  LTX-Video 2.3 生成   │
└──────────────────────────────────────────────┘
```

## 节点配置

| 服务 | 机器 | 配置 | Compose 文件 |
|---|---|---|---|
| n8n + postgres + sau | llm-01 | 任意 | `docker-compose.yml` |
| vLLM (Gemma 4 27B) | llm-01 | RTX 4090 24GB | `docker-compose.vllm.yml` |
| ComfyUI (LTX 2.3) | llm-02 | 16core / 64G / RTX 4090 | `docker-compose.comfyui.yml` |

## 快速开始

### 0. 前置条件

- llm-01 和 llm-02 均安装 Docker + NVIDIA Container Toolkit
- HuggingFace 账号，已接受 [Gemma 4](https://huggingface.co/google/gemma-4-27b-it) 和 [LTX-2.3](https://huggingface.co/Lightricks/LTX-2.3) 使用协议
- 已安装最新版 `huggingface_hub`（CLI 命令为 `hf`，非旧版 `huggingface-cli`）
  ```bash
  pip install -U "huggingface_hub[cli]"
  hf auth login   # 粘贴 HF_TOKEN
  ```
- 两台机器在同一局域网，互相可以通过主机名或 IP 访问

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填写 HF_TOKEN、数据库密码、llm-01/llm-02 的实际 IP 或主机名
vim .env
```

### 2. llm-02：准备 LTX 2.3 模型文件

> **⚠️ 关于显存：** LTX 2.3 原版（22B full / dev）需要 **32GB+ VRAM**，RTX 4090 (24GB) 无法直接运行原版。
> 请使用下方的 **Distilled 版本 + ComfyUI CPU offload** 方案，实测 4090 可跑。

```bash
# 在 llm-02 上执行
mkdir -p ./comfyui-data/models/{checkpoints,text_encoders/gemma-3-12b-it-qat-q4_0-unquantized,loras}
mkdir -p ./comfyui-data/{output,input,custom_nodes}

# ── 主模型：LTX-2.3 Distilled v1.1（约 44GB，4090 需开 CPU offload）──
hf download Lightricks/LTX-2.3 \
  --include "ltx-2.3-22b-distilled-1.1.safetensors" \
  --local-dir ./comfyui-data/models/checkpoints/

# ── Distilled LoRA（约 600MB，让 Distilled 模型质量更好）──
hf download Lightricks/LTX-2.3 \
  --include "ltx-2.3-22b-distilled-lora-384-1.1.safetensors" \
  --local-dir ./comfyui-data/models/loras/

# ── Gemma 3 文字编码器（约 8GB，LTX 2.3 专用，必须下载）──
# 注意：需要整个目录，使用 --repo-type model 下载所有文件
hf download google/gemma-3-12b-it-qat-q4_0-unquantized \
  --local-dir ./comfyui-data/models/text_encoders/gemma-3-12b-it-qat-q4_0-unquantized/

# ── 启动 ComfyUI（带 low VRAM 参数）──
docker compose -f docker-compose.comfyui.yml up -d
# 查看启动日志
docker logs -f vidpipe-comfyui
```

> **磁盘空间提示：** 以上文件合计约 **55GB**，请确保 `./comfyui-data` 所在分区有 **100GB+** 空闲空间。

### 3. llm-01：启动主服务 + vLLM

```bash
# 在 llm-01 上执行

# 先单独创建网络（首次）
docker network create vidpipe 2>/dev/null || true

# 启动 n8n + postgres + sau-backend
docker compose -f docker-compose.yml up -d

# 启动 vLLM（首次启动会从 HuggingFace 下载 Gemma 4，约 15GB）
docker compose -f docker-compose.vllm.yml up -d

# 查看 Gemma 4 加载进度
docker logs -f vidpipe-vllm

# 确认 vLLM 就绪
curl http://localhost:8000/health
# 返回 {"status":"ok"} 即可
```

### 4. 导入 n8n 工作流

1. 打开 `http://llm-01:5678`
2. 进入 **Workflows → Import from File**
3. 选择 `workflow.json`
4. 在 **Settings** 里确认环境变量 `LLM_BASE_URL`、`LLM_MODEL`、`COMFYUI_URL` 已注入

## LTX 2.3 Distilled 在 4090 上的配置建议

| 参数 | 推荐值 | 说明 |
|---|---|---|
| 模型 | `ltx-2.3-22b-distilled-1.1` | Full dev 需要 32GB+，4090 不可用 |
| 分辨率 | 768×1280 (9:16) | 竖版，开 CPU offload 后 4090 可跑 |
| 帧数 | 97 帧 (≈4s @24fps) | 超过 121 帧质量下降 |
| Steps | 8–15 | Distilled 版本步数少，速度快 |
| CFG | 1.0 | Distilled 模型不需要高 CFG |
| ComfyUI 启动参数 | `--lowvram` | 4090 必须加，启用 CPU offload |

## workflow.json 中使用的模型文件对照

| workflow.json 字段 | 实际文件名 | 存放路径 |
|---|---|---|
| `ckpt_name` | `ltx-2.3-22b-distilled-1.1.safetensors` | `models/checkpoints/` |
| `lora_name` | `ltx-2.3-22b-distilled-lora-384-1.1.safetensors` | `models/loras/` |
| `clip_name` (Gemma) | `gemma-3-12b-it-qat-q4_0-unquantized/` (目录) | `models/text_encoders/` |

## 常见问题

**ComfyUI CUDA OOM**  
在 `docker-compose.comfyui.yml` 的 `CLI_ARGS` 里加 `--lowvram`，强制 CPU offload。也可以将分辨率降到 512×896、帧数降到 65。

**`hf: command not found`**  
用 `pip install -U "huggingface_hub[cli]"` 安装/升级，新 CLI 命令是 `hf`，旧版 `huggingface-cli` 已被替代。

**下载 Lightricks/LTX-Video 找不到文件**  
旧的 `Lightricks/LTX-Video` repo 是 LTX-Video 1.x，LTX 2.3 的文件在 `Lightricks/LTX-2.3`。

**vLLM JSON 输出带 markdown 代码块**  
在 system prompt 末尾加：`只输出 JSON 对象本身，不要包含任何 markdown 格式或代码块包裹。`（workflow.json 中已内置）

**n8n 无法访问 llm-02 的 ComfyUI**  
检查 `.env` 里 `COMFYUI_URL` 是否填了 llm-02 的实际 IP，确认防火墙放行 8188 端口。

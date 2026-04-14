# VidPipe — 热点→视频→抖音/小红书 全自动流水线

自动抓取微博/百度热搜，用 LLM 生成文案和提示词，ComfyUI + LTX-Video 2.3 Distilled GGUF 生成竖版短视频，人工审核后自动发布到抖音和小红书。

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
| ComfyUI (LTX 2.3 GGUF) | llm-02 | 16core / 64G / RTX 4090 | `docker-compose.comfyui.yml` |

## 快速开始

### 0. 前置条件

- llm-01 和 llm-02 均安装 Docker + NVIDIA Container Toolkit
- HuggingFace 账号（LTX-2.3 GGUF 和 Gemma 3 GGUF 均为开放权重，无需额外申请协议）
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

### 2. llm-02：准备 LTX 2.3 GGUF 模型文件

> **✅ 4090 友好方案：** 使用 GGUF Q4_K_M 量化版本，显存仅需 ~18GB，无需 CPU offload，生成速度约 **1 分钟/条**。

```bash
# 在 llm-02 上执行
mkdir -p ./comfyui-data/models/{unet,text_encoders,vae,loras,custom_nodes}
mkdir -p ./comfyui-data/{output,input,custom_nodes}

# ── 主模型：LTX-2.3 Distilled GGUF Q4_K_M（约 15.1GB，放 unet/ 目录）──
hf download unsloth/LTX-2.3-GGUF \
  --include "distilled/ltx-2.3-22b-distilled-UD-Q4_K_M.gguf" \
  --local-dir ./comfyui-data/models/unet/

# ── VAE（约 400MB，必须单独下载）──
hf download unsloth/LTX-2.3-GGUF \
  --include "vae/ltx-2.3-22b-dev_video_vae.safetensors" \
  --local-dir ./comfyui-data/models/vae/

# ── Gemma 3 文字编码器 GGUF 版（约 8GB，LTX 2.3 专用）──
hf download unsloth/LTX-2.3-GGUF \
  --include "text_encoders/gemma-3-12b-it-q4_k_m.gguf" \
  --local-dir ./comfyui-data/models/text_encoders/

# ── 安装 ComfyUI-GGUF 自定义节点（GGUF 格式必须）──
docker run --rm -v $(pwd)/comfyui-data/custom_nodes:/target \
  alpine/git clone https://github.com/city96/ComfyUI-GGUF.git /target/ComfyUI-GGUF

# ── 启动 ComfyUI（GGUF 无需 --lowvram）──
docker compose -f docker-compose.comfyui.yml up -d
docker logs -f vidpipe-comfyui
```

> **磁盘空间提示：** 以上文件合计约 **25GB**，远少于 safetensors 版的 55GB。

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

## LTX 2.3 Distilled GGUF 在 4090 上的配置建议

| 参数 | 推荐值 | 说明 |
|---|---|---|
| 模型 | `ltx-2.3-22b-distilled-UD-Q4_K_M.gguf` | 15.1GB，4090 显存充裕，无需 offload |
| 加载节点 | `UnetLoaderGGUF`（ComfyUI-GGUF 插件） | 标准 CheckpointLoader 不支持 GGUF |
| 分辨率 | 768×1280 (9:16) | 竖版，4090 全速运行 |
| 帧数 | 97 帧 (≈4s @24fps) | 超过 121 帧质量下降 |
| Steps | 8–15 | Distilled 版步数少，约 1min/条 |
| CFG | 1.0 | Distilled 模型不需要高 CFG |
| ComfyUI 启动参数 | 无需 `--lowvram` | GGUF 显存占用 ~18GB，4090 绰绰有余 |

## workflow.json 中使用的模型文件对照

| workflow.json 字段 | 实际文件名 | 存放路径 |
|---|---|---|
| `unet_name` (UnetLoaderGGUF) | `distilled/ltx-2.3-22b-distilled-UD-Q4_K_M.gguf` | `models/unet/` |
| `vae_name` | `ltx-2.3-22b-dev_video_vae.safetensors` | `models/vae/` |
| `clip_name` (CLIPLoaderGGUF) | `gemma-3-12b-it-q4_k_m.gguf` | `models/text_encoders/` |

## 常见问题

**`UnetLoaderGGUF` 节点找不到**  
确认 `ComfyUI-GGUF` 自定义节点已安装到 `custom_nodes/ComfyUI-GGUF/`，重启 ComfyUI 后节点会出现在菜单里。

**ComfyUI CUDA OOM**  
将帧数降到 65（约 2.7s），或分辨率降到 512×896，GGUF 版本极少 OOM。

**`hf: command not found`**  
用 `pip install -U "huggingface_hub[cli]"` 安装/升级，新 CLI 命令是 `hf`，旧版 `huggingface-cli` 已被替代。

**vLLM JSON 输出带 markdown 代码块**  
在 system prompt 末尾加：`只输出 JSON 对象本身，不要包含任何 markdown 格式或代码块包裹。`（workflow.json 中已内置）

**n8n 无法访问 llm-02 的 ComfyUI**  
检查 `.env` 里 `COMFYUI_URL` 是否填了 llm-02 的实际 IP，确认防火墙放行 8188 端口。

**下载 Lightricks/LTX-Video 或 Lightricks/LTX-2.3 找不到 GGUF 文件**  
GGUF 量化版由 unsloth 维护，repo 是 `unsloth/LTX-2.3-GGUF`，不在 Lightricks 官方 repo 内。

# VidPipe — 热点→视频→抖音/小红书 全自动流水线

自动抓取微博/百度热搜，用 LLM 生成文案和提示词，ComfyUI + LTX-Video 2.3 生成竖版短视频，人工审核后自动发布到抖音和小红书。

## 架构概览

```
┌──────────────────────────────────────────────┐
│  llm-01（主控节点）                            │
│  ├── n8n          :5678  流程编排              │
│  ├── n8n-runner          Python 执行器         │
│  ├── postgres     :5432  工作流状态存储         │
│  ├── sau-backend  :8080  抖音/小红书发布        │
│  └── vLLM         :8000  Gemma 4 27B IT NF4   │
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
- HuggingFace 账号，已接受 [Gemma 4](https://huggingface.co/google/gemma-4-27b-it) 和 [LTX-Video](https://huggingface.co/Lightricks/LTX-Video) 使用协议
- 两台机器在同一局域网，互相可以通过主机名或 IP 访问

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填写 HF_TOKEN、数据库密码、llm-01/llm-02 的实际 IP 或主机名
vim .env
```

### 2. llm-02：准备 LTX 2.3 模型文件

```bash
# 在 llm-02 上执行
mkdir -p ./comfyui-data/models/{checkpoints,text_encoders,vae,loras}
mkdir -p ./comfyui-data/{output,input,custom_nodes}

# 下载 LTX-Video 2.3 FP8 主模型（约 23GB，4090 推荐版本）
huggingface-cli download Lightricks/LTX-Video \
  --include "ltx-video-2b-v0.9.1-fp8.safetensors" \
  --local-dir ./comfyui-data/models/checkpoints/

# 下载 T5-XXL 文字编码器（必须，约 10GB）
huggingface-cli download Lightricks/LTX-Video \
  --include "t5xxl_fp16.safetensors" \
  --local-dir ./comfyui-data/models/text_encoders/

# 启动 ComfyUI
docker compose -f docker-compose.comfyui.yml up -d
# 查看启动日志
docker logs -f vidpipe-comfyui
```

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

## LTX 2.3 在 4090 上的参数建议

| 参数 | 推荐值 | 说明 |
|---|---|---|  
| 分辨率 | 768×1280 (9:16) | 竖版，4090 可全精度跑 |
| 帧数 | 97 帧 (≈4s @24fps) | 超过 161 帧质量下降 |
| Steps | 30–40 | fp8 版本下质量与速度的平衡点 |
| CFG | 3.5 | LTX 官方推荐值 |
| VAE decode | GPU（不开 CPU offload）| 4090 显存够用 |

## 常见问题

**ComfyUI CUDA OOM**  
在 `docker-compose.comfyui.yml` 的 `CLI_ARGS` 里加 `--fp8_e4m3fn-unet` 或降分辨率到 512×896。

**vLLM JSON 输出带 markdown 代码块**  
在 system prompt 末尾加：`只输出 JSON 对象本身，不要包含任何 markdown 格式或代码块包裹。`

**n8n 无法访问 llm-02 的 ComfyUI**  
检查 `.env` 里 `COMFYUI_URL` 是否填了 llm-02 的实际 IP，确认防火墙放行 8188 端口。
